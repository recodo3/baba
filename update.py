import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"
FEEDS_URL = "https://iptv-org.github.io/api/feeds.json"

STREAM_TIMEOUT = 10
MAX_WORKERS = 20

HINDI_CODES = {"hin"}

# =========================================================
# CHANNELS / NETWORKS WANTED
# =========================================================

TARGET_PATTERNS = {
    "SPORTS": [
        "sony sports ten 1",
        "sony sports ten 2",
        "sony sports ten 3",
        "sony sports ten 4",
        "sony sports ten 5",
        "star sports 1",
        "star sports 2",
        "star sports 3",
        "star sports 1 hindi",
        "star sports 2 hindi",
        "star sports 3 hindi",
        "star sports select 1",
        "star sports select 2",
        "star sports select hd1",
        "star sports select hd2",
        "star sports khel",
    ],

    "MOVIES": [
        "sony max",
        "sony max 2",
        "sony pix",
        "star gold",
        "star gold 2",
        "star gold select",
        "star gold thrills",
        "zee cinema",
        "zee cine classic",
        "zee anmol cinema",
    ],

    "ENTERTAINMENT": [
        "sony entertainment television",
        "sony sab",
        "sony pal",
        "sony wah",
        "sony yay",
        "starplus",
        "star plus",
        "star bharat",
        "star utsav",
        "zee tv",
        "zee anmol",
        "zee zing",
        "zee zest",
    ],

    "FACTUAL & DOCUMENTARY": [
        "discovery",
        "discovery hd",
        "discovery science",
        "discovery science hd",
        "animal planet",
        "animal planet hd",
        "history tv18",
        "history tv18 hd",
    ],
}

# =========================================================
# CHANNELS THAT MUST NEVER ENTER THE PLAYLIST
# =========================================================

EXCLUDED_PATTERNS = [
    "news",
    "business",
    "breaking",
    "headline",
    "headlines",
    "samachar",
    "khabar",
    "suddi",
    "varta",
    "politics",
    "political",
    "financial",
    "times now",
    "wion",
    "aaj tak",
    "abp",
    "etv news",
    "zee news",
    "zee business",
    "sony news",
    "star news",
]

# =========================================================
# NORMALIZATION
# =========================================================

def normalize(value):
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)

    value = str(value or "").lower()

    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def text_from(*values):
    parts = []

    for value in values:
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif value:
            parts.append(str(value))

    return normalize(" ".join(parts))


def matches_any(text, patterns):
    return any(
        normalize(pattern) in text
        for pattern in patterns
    )


# =========================================================
# TARGET CHANNEL IDENTIFICATION
# =========================================================

def get_target_genre(channel, feed, stream):
    channel_name = normalize(channel.get("name"))
    network = normalize(channel.get("network"))
    alt_names = normalize(channel.get("alt_names"))
    feed_name = normalize(feed.get("name") if feed else "")
    feed_alt_names = normalize(feed.get("alt_names") if feed else "")
    stream_title = normalize(stream.get("title"))

    text = " ".join([
        channel_name,
        network,
        alt_names,
        feed_name,
        feed_alt_names,
        stream_title,
    ])

    if matches_any(text, EXCLUDED_PATTERNS):
        return None

    for genre, patterns in TARGET_PATTERNS.items():
        if matches_any(text, patterns):
            return genre

    return None


# =========================================================
# CANONICAL CHANNEL NAME
# =========================================================

def canonical_channel_name(channel, feed=None, stream=None):
    name = channel.get("name") or ""

    name = re.sub(
        r"\s+(hd|sd|fhd|uhd)$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+(hindi|english|tamil|telugu|marathi|bengali)$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(
        r"\s+1080p$",
        "",
        name,
        flags=re.IGNORECASE,
    )

    return re.sub(
        r"\s+",
        " ",
        name
    ).strip()


# =========================================================
# HINDI FEED CHECK
# =========================================================

def is_hindi_feed(feed, channel, stream):
    if feed:
        languages = feed.get("languages", [])

        if isinstance(languages, str):
            languages = [languages]

        languages = {
            normalize(language)
            for language in languages
        }

        if "hin" in languages:
            return True

        return False

    text = text_from(
        channel.get("name"),
        channel.get("alt_names"),
        stream.get("title"),
    )

    return (
        " hindi " in f" {text} "
        or text.endswith(" hindi")
        or "hindi feed" in text
    )


# =========================================================
# HLS HEALTH CHECK
# =========================================================

def request_data(url, headers, timeout=STREAM_TIMEOUT):
    request = Request(
        url,
        headers=headers,
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:

        if not 200 <= response.status < 400:
            return None, None

        content_type = normalize(
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        data = response.read(65536)

        return data, content_type


def check_hls_stream(item):
    url = item["url"]

    headers = {
        "User-Agent": item.get("user_agent") or (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    if item.get("referrer"):
        headers["Referer"] = item["referrer"]

    try:
        data, content_type = request_data(
            url,
            headers,
        )

        if not data:
            return None

        text = data.decode(
            "utf-8",
            errors="ignore",
        )

        if "#EXTM3U" not in text:
            return None

        # -------------------------------------------------
        # MASTER PLAYLIST
        # -------------------------------------------------

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        variant_url = None

        for index, line in enumerate(lines):

            if line.startswith("#EXT-X-STREAM-INF"):

                for next_line in lines[index + 1:]:
                    if not next_line.startswith("#"):
                        variant_url = urljoin(
                            url,
                            next_line,
                        )
                        break

                if variant_url:
                    break

        # -------------------------------------------------
        # MEDIA PLAYLIST / VARIANT PLAYLIST
        # -------------------------------------------------

        media_url = variant_url or url

        if variant_url:

            media_data, _ = request_data(
                variant_url,
                headers,
            )

            if not media_data:
                return None

            media_text = media_data.decode(
                "utf-8",
                errors="ignore",
            )

            if "#EXTM3U" not in media_text:
                return None

        else:
            media_text = text

        # -------------------------------------------------
        # TEST AN ACTUAL MEDIA SEGMENT
        # -------------------------------------------------

        segment_url = None

        for line in media_text.splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            segment_url = urljoin(
                media_url,
                line,
            )

            break

        if segment_url:

            segment_request = Request(
                segment_url,
                headers=headers,
            )

            with urlopen(
                segment_request,
                timeout=STREAM_TIMEOUT,
            ) as segment_response:

                if not (
                    200
                    <= segment_response.status
                    < 400
                ):
                    return None

                segment_data = segment_response.read(
                    4096
                )

                if not segment_data:
                    return None

        return item

    except (
        URLError,
        HTTPError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return None

    except Exception:
        return None


# =========================================================
# DOWNLOAD DATA
# =========================================================

print("Downloading iptv-org data...")

with urlopen(
    STREAMS_URL,
    timeout=30,
) as response:
    streams = json.load(response)

with urlopen(
    CHANNELS_URL,
    timeout=30,
) as response:
    channels = json.load(response)

with urlopen(
    FEEDS_URL,
    timeout=30,
) as response:
    feeds = json.load(response)


# =========================================================
# DATABASES
# =========================================================

channel_map = {
    channel["id"]: channel
    for channel in channels
    if channel.get("id")
}

feed_map = {
    (
        feed.get("channel"),
        feed.get("id"),
    ): feed
    for feed in feeds
    if feed.get("channel")
    and feed.get("id")
}


# =========================================================
# FILTER STREAMS
# =========================================================

candidates = []

stats = {
    "indian": 0,
    "1080p": 0,
    "target": 0,
    "hindi": 0,
    "excluded": 0,
}


for stream in streams:

    channel_id = stream.get("channel")
    url = stream.get("url")

    if not channel_id or not url:
        continue

    channel = channel_map.get(channel_id)

    if not channel:
        continue

    # -----------------------------------------------------
    # INDIA
    # -----------------------------------------------------

    if channel.get("country") != "IN":
        continue

    stats["indian"] += 1

    # -----------------------------------------------------
    # 1080P ONLY
    # -----------------------------------------------------

    quality = normalize(
        stream.get("quality")
    )

    if quality != "1080p":
        continue

    stats["1080p"] += 1

    # -----------------------------------------------------
    # FEED
    # -----------------------------------------------------

    feed_id = stream.get("feed")

    feed = feed_map.get(
        (
            channel_id,
            feed_id,
        )
    )

    # -----------------------------------------------------
    # TARGET CHANNEL
    # -----------------------------------------------------

    genre = get_target_genre(
        channel,
        feed,
        stream,
    )

    if not genre:
        if matches_any(
            text_from(
                channel.get("name"),
                channel.get("network"),
                channel.get("alt_names"),
                stream.get("title"),
            ),
            EXCLUDED_PATTERNS,
        ):
            stats["excluded"] += 1

        continue

    stats["target"] += 1

    # -----------------------------------------------------
    # HINDI ONLY
    # -----------------------------------------------------

    if not is_hindi_feed(
        feed,
        channel,
        stream,
    ):
        continue

    stats["hindi"] += 1

    # -----------------------------------------------------
    # CANONICAL NAME
    # -----------------------------------------------------

    name = canonical_channel_name(
        channel,
        feed,
        stream,
    )

    candidates.append({
        "channel_id": channel_id,
        "feed_id": feed_id,
        "name": name,
        "genre": genre,
        "title": stream.get("title") or name,
        "url": url,
        "user_agent": stream.get("user_agent"),
        "referrer": stream.get("referrer"),
    })


# =========================================================
# DEDUPLICATE CANDIDATE CHANNELS
# =========================================================

unique_candidates = {}

for item in candidates:

    key = normalize(item["name"])

    # Prefer Hindi explicitly named feeds.
    score = 0

    title_text = normalize(
        item["title"]
    )

    if "hindi" in title_text:
        score += 10

    if item["feed_id"]:
        score += 2

    existing = unique_candidates.get(key)

    if not existing:
        unique_candidates[key] = (
            score,
            [item],
        )
    else:
        old_score, old_items = existing

        old_items.append(item)

        unique_candidates[key] = (
            max(old_score, score),
            old_items,
        )


# =========================================================
# FLATTEN UNIQUE CHANNEL CANDIDATES
# =========================================================

test_items = []

for _, (_, items) in unique_candidates.items():

    seen_urls = set()

    for item in items:

        if item["url"] in seen_urls:
            continue

        seen_urls.add(
            item["url"]
        )

        test_items.append(item)


print()
print("=" * 60)
print("FILTER RESULTS")
print("=" * 60)
print(
    f"Indian streams:            {stats['indian']}"
)
print(
    f"Indian 1080p streams:      {stats['1080p']}"
)
print(
    f"Target 1080p streams:      {stats['target']}"
)
print(
    f"Hindi target streams:      {stats['hindi']}"
)
print(
    f"Unique target channels:    {len(unique_candidates)}"
)
print(
    f"URLs to health-check:      {len(test_items)}"
)
print("=" * 60)


# =========================================================
# TEST ALL CANDIDATE URLS
# =========================================================

working = []

print()
print(
    f"Testing {len(test_items)} candidate URLs..."
)
print()

with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = {
        executor.submit(
            check_hls_stream,
            item,
        ): item
        for item in test_items
    }

    for future in as_completed(futures):

        item = futures[future]

        try:
            result = future.result()
        except Exception:
            result = None

        if result:

            print(
                f"WORKING: "
                f"{result['name']} -> "
                f"{result['url']}"
            )

            working.append(result)

        else:

            print(
                f"DEAD: "
                f"{item['name']} -> "
                f"{item['url']}"
            )


# =========================================================
# ONE WORKING URL PER CHANNEL
# =========================================================

best_streams = {}

for item in working:

    key = normalize(
        item["name"]
    )

    if key not in best_streams:
        best_streams[key] = item
        continue

    current = best_streams[key]

    # Prefer:
    # 1. URL with Hindi in title
    # 2. Feed-specific stream
    # 3. Shorter URL as deterministic fallback

    def score(candidate):

        title = normalize(
            candidate["title"]
        )

        value = 0

        if "hindi" in title:
            value += 100

        if candidate.get("feed_id"):
            value += 10

        return value

    if score(item) > score(current):
        best_streams[key] = item


working = list(
    best_streams.values()
)


# =========================================================
# SORT
# =========================================================

genre_order = {
    "SPORTS": 1,
    "MOVIES": 2,
    "ENTERTAINMENT": 3,
    "FACTUAL & DOCUMENTARY": 4,
}

working.sort(
    key=lambda item: (
        genre_order.get(
            item["genre"],
            99,
        ),
        normalize(item["name"]),
    )
)


# =========================================================
# BUILD PLAYLIST
# =========================================================

playlist = [
    "#EXTM3U"
]

current_genre = None

for item in working:

    genre = item["genre"]

    if genre != current_genre:

        current_genre = genre

        playlist.append("")
        playlist.append(
            f"# ===== {genre} ====="
        )
        playlist.append("")

    name = item["name"]

    display_name = name

    if "1080p" not in normalize(
        display_name
    ):
        display_name += " [1080p]"

    if "hindi" not in normalize(
        display_name
    ):
        display_name += " [Hindi]"

    playlist.append(
        '#EXTINF:-1 '
        f'group-title="{genre}",'
        f'{display_name}'
    )

    if item.get("user_agent"):
        playlist.append(
            "#EXTVLCOPT:http-user-agent="
            + item["user_agent"]
        )

    if item.get("referrer"):
        playlist.append(
            "#EXTVLCOPT:http-referrer="
            + item["referrer"]
        )

    playlist.append(
        item["url"]
    )


# =========================================================
# WRITE PLAYLIST
# =========================================================

with open(
    "playlist.m3u",
    "w",
    encoding="utf-8",
    newline="\n",
) as file:

    file.write(
        "\n".join(playlist)
        + "\n"
    )


# =========================================================
# FINAL REPORT
# =========================================================

print()
print("=" * 60)
print("FINAL PLAYLIST")
print("=" * 60)
print(
    f"Unique working channels:   {len(working)}"
)

for genre in (
    "SPORTS",
    "MOVIES",
    "ENTERTAINMENT",
    "FACTUAL & DOCUMENTARY",
):

    count = sum(
        1
        for item in working
        if item["genre"] == genre
    )

    print(
        f"{genre:<28} {count}"
    )

print("=" * 60)
print("playlist.m3u generated successfully.")
print("=" * 60)

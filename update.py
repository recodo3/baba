import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"
FEEDS_URL = "https://iptv-org.github.io/api/feeds.json"

STREAM_TIMEOUT = 8
MAX_WORKERS = 20

HINDI_CODES = {"hin"}

# =========================================================
# ALLOWED NETWORKS / BRANDS
# =========================================================

ALLOWED_NETWORK_KEYWORDS = {
    "sony",
    "star",
    "zee",
    "discovery",
    "history tv18",
    "history tv",
    "animal planet",
}

# =========================================================
# NEVER INCLUDE THESE
# =========================================================

EXCLUDED_KEYWORDS = {
    "news",
    "news hd",
    "business",
    "business news",
    "breaking news",
    "financial news",
    "politics",
    "political",
    "headline",
    "headlines",
    "live news",
    "samachar",
    "khabar",
    "suddi",
    "varta",
    "24x7 news",
}

# =========================================================
# GENRE KEYWORDS
# =========================================================

SPORTS_KEYWORDS = {
    "sports",
    "sport",
    "ten sports",
    "sony sports",
    "star sports",
    "zee sports",
}

MOVIE_KEYWORDS = {
    "movie",
    "movies",
    "cinema",
    "max",
    "pix",
    "gold",
    "gold hd",
}

FACTUAL_KEYWORDS = {
    "discovery",
    "discovery science",
    "discovery turbo",
    "animal planet",
    "history tv18",
    "history tv",
    "science",
    "turbo",
    "investigation discovery",
    "id ",
}

ENTERTAINMENT_KEYWORDS = {
    "entertainment",
    "sab",
    "sony",
    "star plus",
    "star bharat",
    "star utsav",
    "zee tv",
    "zee anmol",
    "zee zing",
}


# =========================================================
# HELPERS
# =========================================================

def normalize(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower()
    )


def combined_text(channel, stream, feed=None):
    values = [
        channel.get("name", ""),
        channel.get("network", ""),
        channel.get("alt_names", ""),
        stream.get("title", ""),
        feed.get("name", "") if feed else "",
    ]

    return normalize(" ".join(map(str, values)))


def contains_any(text, keywords):
    return any(
        keyword in text
        for keyword in keywords
    )


def is_excluded(channel, stream, feed=None):
    text = combined_text(channel, stream, feed)

    return contains_any(
        text,
        EXCLUDED_KEYWORDS
    )


def is_allowed_network(channel, stream):
    text = normalize(
        " ".join([
            str(channel.get("name", "")),
            str(channel.get("network", "")),
            str(channel.get("alt_names", "")),
            str(stream.get("title", "")),
        ])
    )

    return contains_any(
        text,
        ALLOWED_NETWORK_KEYWORDS
    )


def is_hindi_feed(feed):
    languages = feed.get("languages", [])

    if isinstance(languages, str):
        languages = [languages]

    languages = {
        normalize(language)
        for language in languages
    }

    return bool(languages & HINDI_CODES)


def get_genre(channel, stream, feed=None):
    text = combined_text(channel, stream, feed)

    if contains_any(text, SPORTS_KEYWORDS):
        return "SPORTS"

    if contains_any(text, MOVIE_KEYWORDS):
        return "MOVIES"

    if contains_any(text, FACTUAL_KEYWORDS):
        return "FACTUAL & DOCUMENTARY"

    return "ENTERTAINMENT"


def channel_sort_key(item):
    genre_order = {
        "SPORTS": 1,
        "MOVIES": 2,
        "ENTERTAINMENT": 3,
        "FACTUAL & DOCUMENTARY": 4,
    }

    return (
        genre_order.get(item["genre"], 99),
        normalize(item["name"]),
        normalize(item["title"]),
        item["url"],
    )


# =========================================================
# STREAM TEST
# =========================================================

def check_stream(item):
    url = item["url"]
    user_agent = item.get("user_agent")
    referrer = item.get("referrer")

    headers = {
        "User-Agent": user_agent or (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    if referrer:
        headers["Referer"] = referrer

    try:
        request = Request(
            url,
            headers=headers
        )

        with urlopen(
            request,
            timeout=STREAM_TIMEOUT
        ) as response:

            if not (
                200 <= response.status < 400
            ):
                return None

            content_type = normalize(
                response.headers.get(
                    "Content-Type",
                    ""
                )
            )

            data = response.read(16384)

            looks_like_hls = (
                b"#EXTM3U" in data
                or "mpegurl" in content_type
                or "vnd.apple.mpegurl" in content_type
            )

            looks_like_video = (
                "video/" in content_type
            )

            if looks_like_hls or looks_like_video:
                return item

    except (
        URLError,
        HTTPError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        pass

    except Exception:
        pass

    return None


# =========================================================
# DOWNLOAD IPTv-ORG DATA
# =========================================================

print("Downloading iptv-org data...")

with urlopen(STREAMS_URL, timeout=30) as response:
    streams = json.load(response)

with urlopen(CHANNELS_URL, timeout=30) as response:
    channels = json.load(response)

with urlopen(FEEDS_URL, timeout=30) as response:
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
        feed.get("id")
    ): feed
    for feed in feeds
    if feed.get("channel")
    and feed.get("id")
}


# =========================================================
# FILTER BEFORE TESTING
# =========================================================

candidates = []
seen = set()

stats = {
    "indian": 0,
    "allowed_network": 0,
    "hindi": 0,
    "1080p": 0,
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
    # ALLOWED NETWORKS
    # -----------------------------------------------------

    if not is_allowed_network(
        channel,
        stream
    ):
        continue

    stats["allowed_network"] += 1

    # -----------------------------------------------------
    # NEWS / BUSINESS / POLITICAL EXCLUSION
    # -----------------------------------------------------

    if is_excluded(
        channel,
        stream
    ):
        continue

    # -----------------------------------------------------
    # FEED
    # -----------------------------------------------------

    feed_id = stream.get("feed")

    feed = feed_map.get(
        (
            channel_id,
            feed_id
        )
    )

    if not feed:
        continue

    # -----------------------------------------------------
    # HINDI ONLY
    # -----------------------------------------------------

    if not is_hindi_feed(feed):
        continue

    stats["hindi"] += 1

    # -----------------------------------------------------
    # 1080P ONLY
    # -----------------------------------------------------

    if normalize(
        stream.get("quality")
    ) != "1080p":
        continue

    stats["1080p"] += 1

    # -----------------------------------------------------
    # DUPLICATES
    # -----------------------------------------------------

    user_agent = stream.get("user_agent")
    referrer = stream.get("referrer")

    unique_key = (
        channel_id,
        feed_id,
        url,
        user_agent,
        referrer,
    )

    if unique_key in seen:
        continue

    seen.add(unique_key)

    # -----------------------------------------------------
    # PREPARE ENTRY
    # -----------------------------------------------------

    channel_name = (
        channel.get("name")
        or stream.get("title")
        or "Unknown Channel"
    )

    title = (
        stream.get("title")
        or channel_name
    )

    genre = get_genre(
        channel,
        stream,
        feed
    )

    candidates.append({
        "channel_id": channel_id,
        "feed_id": feed_id,
        "name": channel_name,
        "title": title,
        "genre": genre,
        "url": url,
        "user_agent": user_agent,
        "referrer": referrer,
    })


print()
print("=" * 60)
print("FILTER RESULTS")
print("=" * 60)
print(
    f"Indian streams:            {stats['indian']}"
)
print(
    f"Allowed network streams:   {stats['allowed_network']}"
)
print(
    f"Hindi feeds:               {stats['hindi']}"
)
print(
    f"Hindi 1080p candidates:    {stats['1080p']}"
)
print(
    f"Streams to test:            {len(candidates)}"
)
print("=" * 60)


# =========================================================
# PARALLEL STREAM TESTING
# =========================================================

print()
print(
    f"Testing streams with "
    f"{MAX_WORKERS} workers..."
)

working = []

with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = {
        executor.submit(
            check_stream,
            item
        ): item
        for item in candidates
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
                f"{result['name']} "
                f"[{result['genre']}]"
            )

            working.append(result)

        else:
            print(
                f"DEAD: "
                f"{item['name']}"
            )


# =========================================================
# SORT
# =========================================================

working.sort(
    key=channel_sort_key
)


# =========================================================
# BUILD PLAYLIST
# =========================================================

playlist = [
    "#EXTM3U"
]

current_genre = None

genre_headers = {
    "SPORTS": "SPORTS",
    "MOVIES": "MOVIES",
    "ENTERTAINMENT": "ENTERTAINMENT",
    "FACTUAL & DOCUMENTARY": (
        "FACTUAL & DOCUMENTARY"
    ),
}


for item in working:

    genre = item["genre"]

    if genre != current_genre:

        current_genre = genre

        playlist.append("")
        playlist.append(
            f"# ===== {genre_headers[genre]} ====="
        )
        playlist.append("")

    display_name = item["name"]

    if "1080p" not in normalize(display_name):
        display_name += " [1080p]"

    if "hindi" not in normalize(display_name):
        display_name += " [Hindi]"

    playlist.append(
        '#EXTINF:-1 '
        f'group-title="{genre}",'
        f'{display_name}'
    )

    if item["user_agent"]:
        playlist.append(
            "#EXTVLCOPT:http-user-agent="
            + item["user_agent"]
        )

    if item["referrer"]:
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
    newline="\n"
) as file:

    file.write(
        "\n".join(playlist)
        + "\n"
    )


# =========================================================
# REPORT
# =========================================================

print()
print("=" * 60)
print("FINAL PLAYLIST")
print("=" * 60)

print(
    f"Working channels:          {len(working)}"
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

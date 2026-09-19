import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

STREAM_TIMEOUT = 10
MAX_WORKERS = 20


def normalize(value):
    return " ".join(
        str(value or "").strip().lower().split()
    )


def is_discovery_channel(name):
    return "discovery" in normalize(name)


def is_allowed_quality(quality):
    quality = normalize(quality)

    return quality in {
        "1080p",
        "2160p",
    }


def check_stream(item):
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
        request = Request(
            url,
            headers=headers,
        )

        with urlopen(
            request,
            timeout=STREAM_TIMEOUT,
        ) as response:

            if not (
                200 <= response.status < 400
            ):
                return None

            content_type = normalize(
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            data = response.read(16384)

            if not data:
                return None

            is_hls = (
                b"#EXTM3U" in data
                or "mpegurl" in content_type
                or "vnd.apple.mpegurl" in content_type
            )

            is_video = (
                "video/" in content_type
            )

            if is_hls or is_video:
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
# DOWNLOAD SOURCE DATA
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


# =========================================================
# CHANNEL DATABASE
# =========================================================

channel_map = {
    channel["id"]: channel
    for channel in channels
    if channel.get("id")
}


# =========================================================
# FILTER
#
# NORMAL CHANNELS:
#   Only 1080p / 2160p
#
# DISCOVERY CHANNELS:
#   Ignore quality completely.
#   Any Discovery channel is allowed.
# =========================================================

candidates = []

for stream in streams:

    channel_id = stream.get("channel")
    url = stream.get("url")

    if not channel_id:
        continue

    if not url:
        continue

    channel = channel_map.get(channel_id)

    if not channel:
        continue

    channel_name = (
        channel.get("name")
        or stream.get("title")
        or channel_id
    )

    discovery = is_discovery_channel(
        channel_name
    )

    if not discovery:
        if not is_allowed_quality(
            stream.get("quality")
        ):
            continue

    candidates.append({
        "channel_id": channel_id,
        "name": channel_name,
        "title": (
            stream.get("title")
            or channel_name
        ),
        "quality": (
            normalize(stream.get("quality"))
            if stream.get("quality")
            else "unknown"
        ),
        "url": url,
        "user_agent": stream.get("user_agent"),
        "referrer": stream.get("referrer"),
        "discovery": discovery,
    })


# =========================================================
# REMOVE DUPLICATE URLS
# =========================================================

unique_urls = set()
deduplicated_candidates = []

for item in candidates:

    if item["url"] in unique_urls:
        continue

    unique_urls.add(item["url"])
    deduplicated_candidates.append(item)

candidates = deduplicated_candidates


print()
print("=" * 60)
print("FILTER RESULTS")
print("=" * 60)

discovery_count = sum(
    1 for item in candidates
    if item["discovery"]
)

quality_count = len(candidates) - discovery_count

print(
    f"1080p / 2160p candidates: {quality_count}"
)

print(
    f"Discovery candidates:      {discovery_count}"
)

print(
    f"Total candidates:          {len(candidates)}"
)

print("=" * 60)


# =========================================================
# TEST ALL STREAMS
# =========================================================

print()
print(
    f"Testing {len(candidates)} streams..."
)
print()

working = []

with ThreadPoolExecutor(
    max_workers=MAX_WORKERS
) as executor:

    futures = {
        executor.submit(
            check_stream,
            item,
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
                f"WORKING "
                f"{result['name']} "
                f"[{result['quality']}]"
            )

            working.append(result)

        else:

            print(
                f"DEAD "
                f"{item['name']} "
                f"[{item['quality']}]"
            )


# =========================================================
# ONE CHANNEL OF EACH KIND
#
# channel_id is the primary identity.
# Therefore multiple URLs/feeds for the same
# channel become ONE playlist entry.
# =========================================================

unique_channels = {}

for item in working:

    channel_id = item["channel_id"]

    if channel_id not in unique_channels:
        unique_channels[channel_id] = item


working = list(
    unique_channels.values()
)


# =========================================================
# SORT
# =========================================================

working.sort(
    key=lambda item: (
        normalize(item["name"]),
        item["channel_id"],
    )
)


# =========================================================
# BUILD PLAYLIST
# =========================================================

playlist = [
    "#EXTM3U"
]

for item in working:

    display_name = item["name"]
    display_quality = item["quality"]

    playlist.append(
        '#EXTINF:-1 '
        f'group-title="IPTV",'
        f'{display_name} [{display_quality}]'
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

discovery_final = sum(
    1 for item in working
    if item["discovery"]
)

print()
print("=" * 60)
print("FINAL PLAYLIST")
print("=" * 60)

print(
    f"1080p / 2160p candidates: {quality_count}"
)

print(
    f"Discovery candidates:      {discovery_count}"
)

print(
    f"Working streams:           {len(working)}"
)

print(
    f"Unique channels:           {len(working)}"
)

print(
    f"Discovery channels added:  {discovery_final}"
)

print("=" * 60)
print("playlist.m3u generated successfully.")
print("=" * 60)

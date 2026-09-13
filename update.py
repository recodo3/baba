import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

# ONLY these channel families
TARGETS = [
    "star sports",
    "sony",
    "tv18",
    "9xm",
]

STREAM_TIMEOUT = 10


def check_stream(url, user_agent=None, referrer=None):
    """
    Check whether the URL returns something that looks like
    a playable HLS/M3U8 stream.
    """

    headers = {
        "User-Agent": user_agent or "Mozilla/5.0"
    }

    if referrer:
        headers["Referer"] = referrer

    try:
        request = Request(url, headers=headers)

        with urlopen(request, timeout=STREAM_TIMEOUT) as response:

            if not (200 <= response.status < 400):
                return False

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            # Read the beginning of the response
            data = response.read(8192)

            # HLS playlists normally contain #EXTM3U
            if b"#EXTM3U" in data:
                return True

            # Some servers don't provide a useful Content-Type,
            # so also accept obvious video responses.
            if (
                "mpegurl" in content_type
                or "vnd.apple.mpegurl" in content_type
                or "video/" in content_type
            ):
                return True

            return False

    except (
        URLError,
        HTTPError,
        TimeoutError,
        OSError
    ):
        return False

    except Exception:
        return False


print("Downloading iptv-org data...")

with urlopen(STREAMS_URL, timeout=30) as response:
    streams = json.load(response)

with urlopen(CHANNELS_URL, timeout=30) as response:
    channels = json.load(response)


channel_map = {
    channel["id"]: channel
    for channel in channels
    if "id" in channel
}


playlist = ["#EXTM3U"]

seen = set()

for stream in streams:

    channel_id = stream.get("channel")
    url = stream.get("url")

    if not channel_id or not url:
        continue

    channel = channel_map.get(channel_id, {})
    name = channel.get("name", "")

    if not name:
        continue

    name_lower = name.lower()

    # ONLY requested channel families
    if not any(target in name_lower for target in TARGETS):
        continue

    # Stream metadata supplied by iptv-org
    user_agent = stream.get("user_agent")
    referrer = stream.get("referrer")

    # Avoid exact duplicate streams
    unique_key = (
        channel_id,
        url,
        user_agent,
        referrer
    )

    if unique_key in seen:
        continue

    print(f"Testing: {name}")

    if not check_stream(
        url,
        user_agent=user_agent,
        referrer=referrer
    ):
        print(f"SKIPPED: {name}")
        continue

    print(f"WORKING: {name}")

    seen.add(unique_key)

    # M3U metadata
    extinf = f'#EXTINF:-1 group-title="India",{name}'

    playlist.append(extinf)

    # Add VLC-compatible metadata when available
    if user_agent:
        playlist.append(f'#EXTVLCOPT:http-user-agent={user_agent}')

    if referrer:
        playlist.append(f'#EXTVLCOPT:http-referrer={referrer}')

    playlist.append(url)


with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(playlist) + "\n")


print()
print("=" * 50)
print(f"Streams added: {len(seen)}")
print("=" * 50)

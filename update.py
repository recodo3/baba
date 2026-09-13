import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

STREAM_TIMEOUT = 10


def check_stream(url, user_agent=None, referrer=None):
    """
    Check whether the URL returns something that looks
    like a playable HLS/M3U8 stream.
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

            data = response.read(8192)

            if b"#EXTM3U" in data:
                return True

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

    if not url:
        continue

    # ==========================================================
    # ONLY CLOUDPLAY STREAMS
    # ==========================================================

    if "cloudplay" not in url.lower():
        continue

    channel = channel_map.get(channel_id, {})

    name = channel.get("name", "")

    if not name:
        name = stream.get("title", "Unknown Channel")

    user_agent = stream.get("user_agent")
    referrer = stream.get("referrer")
    quality = stream.get("quality")
    title = stream.get("title")

    # Prevent exact duplicate streams
    unique_key = (
        url,
        user_agent,
        referrer
    )

    if unique_key in seen:
        continue

    print(f"Testing: {name}")

    # Test actual stream response
    if not check_stream(
        url,
        user_agent=user_agent,
        referrer=referrer
    ):
        print(f"SKIPPED: {name}")
        continue

    print(f"WORKING: {name}")

    seen.add(unique_key)

    # Use stream title when available
    display_name = title or name

    if quality:
        display_name = f"{display_name} [{quality}]"

    playlist.append(
        f'#EXTINF:-1 group-title="CloudPlay",{display_name}'
    )

    # Preserve required VLC headers
    if user_agent:
        playlist.append(
            f'#EXTVLCOPT:http-user-agent={user_agent}'
        )

    if referrer:
        playlist.append(
            f'#EXTVLCOPT:http-referrer={referrer}'
        )

    playlist.append(url)


with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(playlist) + "\n")


print()
print("=" * 60)
print(f"CloudPlay streams added: {len(seen)}")
print("=" * 60)

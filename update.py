import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

STREAM_TIMEOUT = 10


def check_stream(url, user_agent=None, referrer=None):
    """
    Check whether the stream responds and looks like
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

            data = response.read(8192)

            # HLS playlist
            if b"#EXTM3U" in data:
                return True

            # HLS/video content types
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


# ---------------------------------------------------------
# CHANNEL DATABASE
# ---------------------------------------------------------

channel_map = {
    channel["id"]: channel
    for channel in channels
    if "id" in channel
}


# ---------------------------------------------------------
# PLAYLIST
# ---------------------------------------------------------

playlist = ["#EXTM3U"]

seen = set()

total_indian = 0
total_1080p = 0
total_working = 0


# ---------------------------------------------------------
# PROCESS STREAMS
# ---------------------------------------------------------

for stream in streams:

    channel_id = stream.get("channel")
    url = stream.get("url")

    if not channel_id or not url:
        continue


    # -----------------------------------------------------
    # GET CHANNEL INFORMATION
    # -----------------------------------------------------

    channel = channel_map.get(channel_id)

    if not channel:
        continue


    # -----------------------------------------------------
    # CONDITION 1:
    # ONLY INDIAN CHANNELS
    # -----------------------------------------------------

    country = channel.get("country")

    if country != "IN":
        continue

    total_indian += 1


    # -----------------------------------------------------
    # CONDITION 2:
    # ONLY 1080P
    # -----------------------------------------------------

    quality = stream.get("quality")

    if quality != "1080p":
        continue

    total_1080p += 1


    # -----------------------------------------------------
    # CHANNEL NAME
    # -----------------------------------------------------

    name = channel.get("name", "")

    if not name:
        name = stream.get("title", "Unknown Channel")


    # -----------------------------------------------------
    # STREAM INFORMATION
    # -----------------------------------------------------

    user_agent = stream.get("user_agent")
    referrer = stream.get("referrer")
    title = stream.get("title")


    # -----------------------------------------------------
    # PREVENT EXACT DUPLICATES
    # -----------------------------------------------------

    unique_key = (
        channel_id,
        url,
        user_agent,
        referrer
    )

    if unique_key in seen:
        continue


    # -----------------------------------------------------
    # TEST STREAM
    # -----------------------------------------------------

    print(f"Testing 1080p: {name}")

    if not check_stream(
        url,
        user_agent=user_agent,
        referrer=referrer
    ):
        print(f"SKIPPED: {name}")
        continue


    print(f"WORKING 1080p: {name}")

    seen.add(unique_key)
    total_working += 1


    # -----------------------------------------------------
    # DISPLAY NAME
    # -----------------------------------------------------

    display_name = title or name

    # Make sure playlist clearly shows 1080p
    if "1080p" not in display_name.lower():
        display_name = f"{display_name} [1080p]"


    # -----------------------------------------------------
    # ADD TO PLAYLIST
    # -----------------------------------------------------

    playlist.append(
        f'#EXTINF:-1 group-title="India 1080p",{display_name}'
    )


    # -----------------------------------------------------
    # PRESERVE VLC HEADERS
    # -----------------------------------------------------

    if user_agent:
        playlist.append(
            f'#EXTVLCOPT:http-user-agent={user_agent}'
        )

    if referrer:
        playlist.append(
            f'#EXTVLCOPT:http-referrer={referrer}'
        )


    playlist.append(url)


# ---------------------------------------------------------
# WRITE PLAYLIST
# ---------------------------------------------------------

with open(
    "playlist.m3u",
    "w",
    encoding="utf-8"
) as f:

    f.write("\n".join(playlist) + "\n")


# ---------------------------------------------------------
# REPORT
# ---------------------------------------------------------

print()
print("=" * 60)
print("INDIA 1080P PLAYLIST")
print("=" * 60)

print(f"Indian streams found:       {total_indian}")
print(f"Indian 1080p streams:       {total_1080p}")
print(f"Working 1080p streams:      {total_working}")

print("=" * 60)

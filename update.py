import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

# ONLY these channel families
TARGETS = [
    "star sports",
    "discovery",
    "history tv",
    "9xm",
]

# How long to wait for a stream to respond
STREAM_TIMEOUT = 8


def stream_is_alive(url):
    """Check whether the stream URL responds."""

    try:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urlopen(request, timeout=STREAM_TIMEOUT) as response:
            status = response.status

            if 200 <= status < 400:
                return True

    except (URLError, HTTPError, TimeoutError, OSError):
        pass
    except Exception:
        pass

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

    # Avoid duplicate streams
    unique_key = (channel_id, url)

    if unique_key in seen:
        continue

    print(f"Testing: {name}")

    # Test stream before adding it
    if not stream_is_alive(url):
        print(f"SKIPPED (not reachable): {name}")
        continue

    print(f"WORKING: {name}")

    seen.add(unique_key)

    playlist.append(
        f'#EXTINF:-1 group-title="India",{name}'
    )

    playlist.append(url)


with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(playlist) + "\n")


print(f"Streams added: {len(seen)}")

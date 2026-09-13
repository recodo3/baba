import json
from urllib.request import urlopen

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

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

# ONLY these channel families
TARGETS = [
    "star sports",
    "discovery",
    "history",
    "9xm",
]

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

    # Include ONLY requested channel families
    if not any(target in name_lower for target in TARGETS):
        continue

    # Avoid duplicate channel + stream combinations
    unique_key = (channel_id, url)

    if unique_key in seen:
        continue

    seen.add(unique_key)

    playlist.append(
        f'#EXTINF:-1 group-title="India",{name}'
    )
    playlist.append(url)

    print(f"FOUND: {name}")

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(playlist) + "\n")

print(f"Streams added: {len(seen)}")

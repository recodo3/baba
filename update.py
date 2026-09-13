import json
import urllib.request

CHANNELS = {
    "StarSports1Hindi.in@HD": "Star Sports 1 HD Hindi",
    "DiscoveryChannel.in@SD": "Discovery Channel",
    "9XM.in@SD": "9XM",
}

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"

print("Downloading current iptv-org stream data...")

with urllib.request.urlopen(STREAMS_URL) as response:
    streams = json.load(response)

playlist = ["#EXTM3U"]

found = set()

for stream in streams:
    channel_id = stream.get("channel")

    if channel_id not in CHANNELS:
        continue

    url = stream.get("url")

    if not url:
        continue

    name = CHANNELS[channel_id]
    quality = stream.get("quality") or ""

    playlist.append(
        f'#EXTINF:-1 tvg-id="{channel_id}" group-title="Hindi",'
        f'{name} {f"({quality})" if quality else ""}'
    )

    if stream.get("referrer"):
        playlist.append(f'#EXTVLCOPT:http-referrer={stream["referrer"]}')

    if stream.get("user_agent"):
        playlist.append(f'#EXTVLCOPT:http-user-agent={stream["user_agent"]}')

    playlist.append(url)
    found.add(channel_id)

with open("playlist.m3u", "w", encoding="utf-8") as file:
    file.write("\n".join(playlist) + "\n")

print()
print("Playlist created.")
print()

for channel_id, name in CHANNELS.items():
    if channel_id in found:
        print(f"FOUND: {name}")
    else:
        print(f"NOT FOUND: {name}")

print()
print(f"Total streams added: {len(found)}")

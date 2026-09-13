import json
import urllib.request

TARGETS = {
    "Star Sports 1 Hindi": ["starsports1hindi", "star sports 1 hindi"],
    "Discovery": ["discovery"],
    "9XM": ["9xm"],
}

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

def download_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)

print("Downloading iptv-org data...")

streams = download_json(STREAMS_URL)
channels = download_json(CHANNELS_URL)

channel_names = {}

for channel in channels:
    channel_id = channel.get("id", "")
    name = channel.get("name", "")
    alt_names = channel.get("alt_names", [])

    channel_names[channel_id] = " ".join(
        [channel_id, name] + alt_names
    ).lower()

playlist = ["#EXTM3U"]
added = set()

for stream in streams:
    channel_id = stream.get("channel") or ""
    title = stream.get("title") or ""
    
    searchable = (
        channel_id + " " +
        title + " " +
        channel_names.get(channel_id, "")
    ).lower()

    matched = None

    for target, keywords in TARGETS.items():
        if target in added:
            continue

        # Require the important identifying words.
        if target == "Star Sports 1 Hindi":
            if "star sports 1 hindi" in searchable:
                matched = target

        elif target == "9XM":
            if "9xm" in searchable:
                matched = target

        elif target == "Discovery":
            if "discovery" in searchable:
                matched = target

        if matched:
            break

    if not matched:
        continue

    url = stream.get("url")

    if not url:
        continue

    display_name = matched

    quality = stream.get("quality")
    if quality:
        display_name += f" ({quality})"

    playlist.append(
        f'#EXTINF:-1 group-title="Hindi",'
        f'{display_name}'
    )

    referrer = stream.get("referrer")
    if referrer:
        playlist.append(f'#EXTVLCOPT:http-referrer={referrer}')

    user_agent = stream.get("user_agent")
    if user_agent:
        playlist.append(f'#EXTVLCOPT:http-user-agent={user_agent}')

    playlist.append(url)

    added.add(matched)

print()
print("Results:")

for target in TARGETS:
    if target in added:
        print(f"FOUND: {target}")
    else:
        print(f"NOT FOUND: {target}")

print()

with open("playlist.m3u", "w", encoding="utf-8") as f:
    f.write("\n".join(playlist) + "\n")

print(f"Streams added: {len(added)}")

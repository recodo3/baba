import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"
FEEDS_URL = "https://iptv-org.github.io/api/feeds.json"

STREAM_TIMEOUT = 10

# =========================================================
# YOUR CHANNEL POLICY
# =========================================================

ALLOWED_NETWORKS = {
    "Sony",
    "Star",
    "Discovery",
    "History TV18",
    "Animal Planet",
}

# Explicitly reject these regardless of network
EXCLUDED_KEYWORDS = {
    "news",
    "business",
    "breaking news",
    "politics",
    "financial news",
}

# Hindi ISO 639-3 code
HINDI_CODE = "hin"


# =========================================================
# STREAM CHECK
# =========================================================

def check_stream(url, user_agent=None, referrer=None):

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


# =========================================================
# DOWNLOAD DATA
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
    if "id" in channel
}

feed_map = {
    (feed.get("channel"), feed.get("id")): feed
    for feed in feeds
    if feed.get("channel") and feed.get("id")
}


# =========================================================
# HELPERS
# =========================================================

def normalize(text):
    return " ".join(
        str(text or "").lower().split()
    )


def is_news_channel(channel, stream):

    values = [
        channel.get("name", ""),
        channel.get("network", ""),
        stream.get("title", ""),
    ]

    text = normalize(" ".join(values))

    return any(
        keyword in text
        for keyword in EXCLUDED_KEYWORDS
    )


def is_allowed_network(channel):

    network = normalize(channel.get("network"))

    name = normalize(channel.get("name"))

    # Network-based matching
    for allowed in ALLOWED_NETWORKS:

        allowed_normalized = normalize(allowed)

        if (
            allowed_normalized in network
            or allowed_normalized in name
        ):
            return True

    return False


def is_hindi_feed(feed):

    languages = feed.get("languages", [])

    return HINDI_CODE in languages


# =========================================================
# PLAYLIST
# =========================================================

playlist = ["#EXTM3U"]

seen = set()

total_indian = 0
total_allowed = 0
total_hindi = 0
total_1080p = 0
total_working = 0


# =========================================================
# PROCESS STREAMS
# =========================================================

for stream in streams:

    channel_id = stream.get("channel")
    url = stream.get("url")

    if not channel_id or not url:
        continue


    # -----------------------------------------------------
    # CHANNEL
    # -----------------------------------------------------

    channel = channel_map.get(channel_id)

    if not channel:
        continue


    # -----------------------------------------------------
    # INDIA
    # -----------------------------------------------------

    if channel.get("country") != "IN":
        continue

    total_indian += 1


    # -----------------------------------------------------
    # ALLOWED NETWORK
    # -----------------------------------------------------

    if not is_allowed_network(channel):
        continue

    total_allowed += 1


    # -----------------------------------------------------
    # REMOVE NEWS
    # -----------------------------------------------------

    if is_news_channel(channel, stream):
        continue


    # -----------------------------------------------------
    # FEED
    # -----------------------------------------------------

    feed_id = stream.get("feed")

    feed = feed_map.get(
        (channel_id, feed_id)
    )

    if not feed:
        continue


    # -----------------------------------------------------
    # HINDI ONLY
    # -----------------------------------------------------

    if not is_hindi_feed(feed):
        continue

    total_hindi += 1


    # -----------------------------------------------------
    # 1080P ONLY
    # -----------------------------------------------------

    if stream.get("quality") != "1080p":
        continue

    total_1080p += 1


    # -----------------------------------------------------
    # STREAM INFO
    # -----------------------------------------------------

    name = channel.get(
        "name",
        stream.get("title", "Unknown Channel")
    )

    title = stream.get("title")

    user_agent = stream.get("user_agent")
    referrer = stream.get("referrer")


    # -----------------------------------------------------
    # DUPLICATE PROTECTION
    # -----------------------------------------------------

    unique_key = (
        channel_id,
        feed_id,
        url,
        user_agent,
        referrer
    )

    if unique_key in seen:
        continue

    seen.add(unique_key)


    # -----------------------------------------------------
    # TEST STREAM
    # -----------------------------------------------------

    print(f"Testing Hindi 1080p: {name}")

    if not check_stream(
        url,
        user_agent=user_agent,
        referrer=referrer
    ):
        print(f"SKIPPED: {name}")
        continue


    print(f"WORKING Hindi 1080p: {name}")

    total_working += 1


    # -----------------------------------------------------
    # DISPLAY NAME
    # -----------------------------------------------------

    display_name = title or name

    if "1080p" not in display_name.lower():
        display_name += " [1080p]"

    if "hindi" not in display_name.lower():
        display_name += " [Hindi]"


    # -----------------------------------------------------
    # M3U
    # -----------------------------------------------------

    playlist.append(
        f'#EXTINF:-1 group-title="India Hindi 1080p",{display_name}'
    )

    if user_agent:
        playlist.append(
            f'#EXTVLCOPT:http-user-agent={user_agent}'
        )

    if referrer:
        playlist.append(
            f'#EXTVLCOPT:http-referrer={referrer}'
        )

    playlist.append(url)


# =========================================================
# WRITE PLAYLIST
# =========================================================

with open(
    "playlist.m3u",
    "w",
    encoding="utf-8"
) as f:

    f.write("\n".join(playlist) + "\n")


# =========================================================
# REPORT
# =========================================================

print()
print("=" * 60)
print("INDIA HINDI 1080P PLAYLIST")
print("=" * 60)

print(f"Indian streams found:       {total_indian}")
print(f"Allowed network streams:   {total_allowed}")
print(f"Hindi feeds:                {total_hindi}")
print(f"Hindi 1080p streams:        {total_1080p}")
print(f"Working Hindi 1080p:        {total_working}")

print("=" * 60)

import re

HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@(\w+)", re.UNICODE)


def extract_hashtags(text: str) -> list[str]:
    """Returns list of hashtag values (without #), lowercased."""
    return [m.lower() for m in HASHTAG_RE.findall(text)]


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text)


def extract_mentions(text: str) -> list[str]:
    return MENTION_RE.findall(text)


def is_only_hashtag(text: str) -> str | None:
    """If the message is just a single hashtag (possibly with whitespace), return the tag."""
    stripped = text.strip()
    m = re.fullmatch(r"#(\w+)", stripped)
    return m.group(1).lower() if m else None


def is_only_url(text: str) -> str | None:
    """If the message is just a URL, return it."""
    stripped = text.strip()
    m = re.fullmatch(r"https?://\S+", stripped, re.IGNORECASE)
    return stripped if m else None


def normalize_tag(tag: str) -> str:
    return tag.lower().lstrip("#")

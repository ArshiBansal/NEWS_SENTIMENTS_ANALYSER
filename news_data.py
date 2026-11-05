from datetime import datetime, timezone
from xml.etree import ElementTree
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup
from dateutil import parser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_FEED_BYTES = 5 * 1024 * 1024
analyzer = SentimentIntensityAnalyzer()


def parse_published_date(value):
    if not value:
        return None

    cleaned = (
        value.strip()
        .replace("GMT", "+0000")
        .replace("UTC", "+0000")
        .replace("PDT", "-0700")
        .replace("PST", "-0800")
        .replace("EST", "-0500")
        .replace("EDT", "-0400")
    )
    try:
        parsed_date = parser.parse(cleaned)
    except (OverflowError, TypeError, ValueError):
        return None

    if parsed_date.tzinfo is None:
        parsed_date = parsed_date.replace(tzinfo=timezone.utc)
    return parsed_date.astimezone(timezone.utc)


def get_relative_time(value, now=None):
    published = parse_published_date(value)
    if published is None:
        return "Age unknown"

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_seconds = (now.astimezone(timezone.utc) - published).total_seconds()

    if delta_seconds < 0:
        return "In the future"
    if delta_seconds < 60:
        return "Just now"
    if delta_seconds < 3600:
        minutes = int(delta_seconds // 60)
        return f"{minutes} min{'s' if minutes != 1 else ''} ago"
    if delta_seconds < 86400:
        hours = int(delta_seconds // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(delta_seconds // 86400)
    if days <= 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return published.strftime("%d %b %Y")


def classify_article(title, summary, is_crypto):
    text = f"{title} {summary}".lower()
    if is_crypto:
        if any(word in text for word in ("bitcoin", "btc")):
            return "Bitcoin & Major Coins"
        if any(word in text for word in ("defi", "uniswap", "aave", "stablecoin", "usdt", "usdc")):
            return "DeFi & Stablecoins"
        if any(word in text for word in ("sec", "regulation", "etf", "cftc", "ban", "tax", "policy")):
            return "Regulation & Policy"
        if any(word in text for word in ("nft", "gaming", "metaverse")):
            return "NFTs & Gaming"
        return "Markets & Trading"

    if any(word in text for word in ("apple", "microsoft", "nvidia", "google", "meta", "technology", " ai ")):
        return "Technology & IT"
    if any(word in text for word in ("earning", "quarter", "revenue", "profit")):
        return "Earnings & Companies"
    if any(word in text for word in ("fed", "inflation", "rate", "gdp", "jobs", "economy")):
        return "Macro & Economy"
    if any(word in text for word in ("bank", "jpmorgan", "financial", "goldman")):
        return "Financials & Banking"
    return "Markets & Indices"


def _element_text(item, name):
    matching_elements = [
        child
        for child in item
        if child.tag.rsplit("}", 1)[-1].lower() == name.lower()
    ]
    if name.lower() == "link":
        element = next(
            (
                child
                for child in matching_elements
                if child.get("rel", "alternate").lower() == "alternate"
            ),
            matching_elements[0] if matching_elements else None,
        )
    else:
        element = matching_elements[0] if matching_elements else None
    if element is None:
        return ""
    if name.lower() == "link" and element.get("href"):
        return element.get("href").strip()
    value = " ".join("".join(element.itertext()).split())
    if "<" not in value:
        return value
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _valid_article_url(value):
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return value.strip()


def fetch_feed(url, source, is_crypto):
    """Fetch and normalize one RSS feed. Returns (articles, error_message)."""
    response = None
    try:
        response = requests.get(url, timeout=15, headers=HEADERS, stream=True)
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_FEED_BYTES:
                return [], f"{source} feed exceeded the 5 MB size limit."

        root = ElementTree.fromstring(content)
        entries = [
            element for element in root.iter()
            if element.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")
        ]
        articles = []
        for item in entries[:40]:
            title = _element_text(item, "title")
            if not title:
                continue

            summary = (
                _element_text(item, "description")
                or _element_text(item, "summary")
                or _element_text(item, "content")
            )
            link = _valid_article_url(_element_text(item, "link"))
            pub_date = (
                _element_text(item, "pubDate")
                or _element_text(item, "published")
                or _element_text(item, "updated")
                or _element_text(item, "date")
            )
            score = analyzer.polarity_scores(f"{title} {summary}")["compound"]
            sentiment = "Positive" if score >= 0.1 else "Negative" if score <= -0.1 else "Neutral"
            articles.append({
                "title": title,
                "summary": summary[:280] + ("..." if len(summary) > 280 else ""),
                "link": link,
                "sentiment": sentiment,
                "compound": score,
                "source": source,
                "pubDate": pub_date,
                "category": classify_article(title, summary, is_crypto),
            })

        if not articles:
            return [], f"{source} returned no readable articles."
        return articles, ""
    except requests.RequestException as error:
        return [], f"{source} could not be loaded: {error}"
    except (ElementTree.ParseError, UnicodeError) as error:
        return [], f"{source} returned invalid RSS data: {error}"
    finally:
        if response is not None:
            response.close()

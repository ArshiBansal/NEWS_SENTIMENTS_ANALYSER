from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests
import spacy
from bs4 import BeautifulSoup
from dateutil import parser
from deep_translator import GoogleTranslator  # type: ignore[import-untyped]
from langdetect import LangDetectException, detect  # type: ignore[import-untyped]
from rapidfuzz import fuzz
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore[import-untyped]

FeedTuple = tuple[str, str, bool, str]  # url, source, is_crypto, feed_type

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_FEED_BYTES: int = 5 * 1024 * 1024
MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 1.0

# Time thresholds (seconds)
SECONDS_PER_MINUTE: int = 60
SECONDS_PER_HOUR: int = 3600
SECONDS_PER_DAY: int = 86400
DAYS_PER_WEEK: int = 7

# VADER sentiment thresholds
SENTIMENT_POSITIVE_THRESHOLD: float = 0.1
SENTIMENT_NEGATIVE_THRESHOLD: float = -0.1
SUMMARY_MAX_LENGTH: int = 280

# Fuzzy deduplication threshold (0-100)
DEDUP_TITLE_THRESHOLD: int = 85
DEDUP_TITLE_SOURCE_THRESHOLD: int = 90

analyzer: SentimentIntensityAnalyzer = SentimentIntensityAnalyzer()

# spaCy NER model (loaded lazily)
_nlp: Any | None = None

# Entity types to extract
ENTITY_TYPES: set[str] = {
    "ORG",      # Organizations (companies, agencies)
    "PERSON",   # People
    "GPE",      # Geopolitical entities (countries, cities)
    "MONEY",    # Monetary values
    "PERCENT",  # Percentages
    "DATE",     # Dates
    "PRODUCT",  # Products
    "EVENT",    # Events
}

ArticleDict = dict[str, Any]


def _get_nlp() -> Any:
    """Lazily load spaCy model, downloading to writable location if needed."""
    global _nlp
    if _nlp is None:
        # Try loading normally first
        try:
            _nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "lemmatizer"])
            return _nlp
        except OSError:
            pass

        # Download model to a writable directory using SPACY_HOME
        import subprocess
        import sys
        import os
        from pathlib import Path

        model_dir = Path(os.environ.get("SPACY_MODEL_DIR", "/tmp/spacy_models"))
        model_dir.mkdir(parents=True, exist_ok=True)

        # Set SPACY_HOME so spacy downloads to our directory
        env = os.environ.copy()
        env["SPACY_HOME"] = str(model_dir)

        # Find existing model in our directory (spacy creates versioned subdirs)
        def find_model_path(base: Path) -> Path | None:
            for p in base.rglob("en_core_web_sm"):
                if p.is_dir() and (p / "config.cfg").exists():
                    return p
            return None

        model_path = find_model_path(model_dir)
        if model_path:
            _nlp = spacy.load(str(model_path), disable=["parser", "tagger", "lemmatizer"])
            return _nlp

        # Download using spacy CLI with SPACY_HOME set
        try:
            subprocess.check_call([
                sys.executable, "-m", "spacy", "download", "en_core_web_sm"
            ], env=env, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            # spaCy download failed - create a dummy NLP that returns no entities
            import warnings
            warnings.warn(f"spaCy model download failed: {e}. Entity extraction disabled.")
            _nlp = _DummyNLP()
            return _nlp

        # Find the downloaded model (spacy creates versioned subdirectory)
        model_path = find_model_path(model_dir)
        if not model_path:
            raise RuntimeError(f"spaCy model not found in {model_dir} after download")

        _nlp = spacy.load(str(model_path), disable=["parser", "tagger", "lemmatizer"])
    return _nlp


class _DummyNLP:
    """Fallback NLP that returns no entities when spaCy is unavailable."""
    def __call__(self, text: str) -> Any:
        class _DummyDoc:
            ents = []
        return _DummyDoc()
    
    def pipe(self, texts, **kwargs):
        for _ in texts:
            yield self("")


def extract_entities(text: str) -> list[dict[str, str]]:
    """Extract named entities from text using spaCy NER."""
    nlp = _get_nlp()
    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        if ent.label_ in ENTITY_TYPES:
            entities.append({"text": ent.text, "label": ent.label_})
    return entities


def parse_published_date(value: str | None) -> datetime | None:
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


def get_relative_time(value: str | None, now: datetime | None = None) -> str:
    published = parse_published_date(value)
    if published is None:
        return "Age unknown"

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_seconds = (now.astimezone(timezone.utc) - published).total_seconds()

    if delta_seconds < 0:
        result = "In the future"
    elif delta_seconds < SECONDS_PER_MINUTE:
        result = "Just now"
    elif delta_seconds < SECONDS_PER_HOUR:
        minutes = int(delta_seconds // SECONDS_PER_MINUTE)
        result = f"{minutes} min{'s' if minutes != 1 else ''} ago"
    elif delta_seconds < SECONDS_PER_DAY:
        hours = int(delta_seconds // SECONDS_PER_HOUR)
        result = f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(delta_seconds // SECONDS_PER_DAY)
        if days <= DAYS_PER_WEEK:
            result = f"{days} day{'s' if days != 1 else ''} ago"
        else:
            result = published.strftime("%d %b %Y")

    return result


def classify_article(title: str, summary: str, is_crypto: bool) -> str:
    text = f"{title} {summary}".lower()
    category = "Markets & Trading" if is_crypto else "Markets & Indices"

    if is_crypto:
        if any(word in text for word in ("bitcoin", "btc")):
            category = "Bitcoin & Major Coins"
        elif any(
            word in text
            for word in ("defi", "uniswap", "aave", "stablecoin", "usdt", "usdc")
        ):
            category = "DeFi & Stablecoins"
        elif any(
            word in text
            for word in ("sec", "regulation", "etf", "cftc", "ban", "tax", "policy")
        ):
            category = "Regulation & Policy"
        elif any(word in text for word in ("nft", "gaming", "metaverse")):
            category = "NFTs & Gaming"
    else:  # noqa: PLR5501
        if any(
            word in text
            for word in ("apple", "microsoft", "nvidia", "google", "meta", "technology", " ai ")
        ):
            category = "Technology & IT"
        elif any(word in text for word in ("earning", "quarter", "revenue", "profit")):
            category = "Earnings & Companies"
        elif any(word in text for word in ("fed", "inflation", "rate", "gdp", "jobs", "economy")):
            category = "Macro & Economy"
        elif any(word in text for word in ("bank", "jpmorgan", "financial", "goldman")):
            category = "Financials & Banking"

    return category


def deduplicate_articles(articles: list[ArticleDict]) -> list[ArticleDict]:
    """Remove near-duplicate articles using fuzzy title matching.

    Articles are considered duplicates if:
    - Titles are very similar (>= DEDUP_TITLE_THRESHOLD) from same source, or
    - Titles are extremely similar (>= DEDUP_TITLE_SOURCE_THRESHOLD) across sources
    """
    if not articles:
        return []

    deduplicated: list[ArticleDict] = []
    seen_titles: list[tuple[str, str]] = []  # (normalized_title, source)

    for article in articles:
        title = article["title"].strip().lower()
        source = article["source"].lower()

        is_duplicate = False
        for seen_title, seen_source in seen_titles:
            # Same source: stricter threshold
            threshold = (
                DEDUP_TITLE_SOURCE_THRESHOLD
                if source == seen_source
                else DEDUP_TITLE_THRESHOLD
            )
            if fuzz.ratio(title, seen_title) >= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            deduplicated.append(article)
            seen_titles.append((title, source))

    return deduplicated


def extract_entities(text: str) -> list[dict[str, str]]:
    """Extract named entities from text using spaCy NER.

    Returns list of dicts with 'text', 'label', 'description' keys.
    """
    if not text or not text.strip():
        return []

    nlp = _get_nlp()
    doc = nlp(text[:1000])  # Limit to first 1000 chars for performance

    entities = []
    for ent in doc.ents:
        if ent.label_ in ENTITY_TYPES:
            entities.append({
                "text": ent.text,
                "label": ent.label_,
                "description": spacy.explain(ent.label_) or ent.label_,  # type: ignore[attr-defined,no-untyped-call]
            })

    # Deduplicate entities by text+label
    seen: set[tuple[str, str]] = set()
    unique_entities = []
    for ent in entities:
        key = (ent["text"].lower(), ent["label"])
        if key not in seen:
            seen.add(key)
            unique_entities.append(ent)

    return unique_entities


# Language detection and translation
_translator: GoogleTranslator | None = None


def _get_translator() -> GoogleTranslator:
    """Lazily initialize translator."""
    global _translator
    if _translator is None:
        _translator = GoogleTranslator(source="auto", target="en")
    return _translator


def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Returns ISO 639-1 language code (e.g., 'en', 'es', 'fr') or 'unknown'.
    """
    if not text or not text.strip():
        return "unknown"
    try:
        return detect(text[:500])  # type: ignore[no-any-return]  # Use first 500 chars for detection
    except LangDetectException:
        return "unknown"


def translate_to_english(text: str, source_lang: str | None = None) -> str:
    """Translate text to English.

    If source_lang is provided, use it; otherwise auto-detect.
    Returns original text if translation fails or text is already English.
    """
    if not text or not text.strip():
        return text

    if source_lang == "en" or source_lang == "english":
        return text

    try:
        translator = _get_translator()
        if source_lang and source_lang != "auto":
            translator = GoogleTranslator(source=source_lang, target="en")
        return translator.translate(text[:5000])  # type: ignore[no-any-return]  # Limit to 5000 chars
    except Exception:
        return text


def process_article_text(text: str) -> dict[str, Any]:
    """Detect language and translate article text to English if needed.

    Returns dict with 'original_text', 'translated_text', 'language', 'was_translated'.
    """
    if not text or not text.strip():
        return {
            "original_text": text,
            "translated_text": text,
            "language": "unknown",
            "was_translated": False,
        }

    language = detect_language(text)
    if language == "en" or language == "english" or language == "unknown":
        return {
            "original_text": text,
            "translated_text": text,
            "language": language,
            "was_translated": False,
        }

    translated = translate_to_english(text, language)
    return {
        "original_text": text,
        "translated_text": translated,
        "language": language,
        "was_translated": translated != text,
    }


def _element_text(item: ElementTree.Element, name: str) -> str:
    matching_elements = [
        child for child in item if child.tag.rsplit("}", 1)[-1].lower() == name.lower()
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
        href = element.get("href")
        return href.strip() if href else ""
    value = " ".join("".join(element.itertext()).split())
    if "<" not in value:
        return value
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _valid_article_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return value.strip()


def fetch_feed(url: str, source: str, is_crypto: bool) -> tuple[list[ArticleDict], str]:
    """Fetch and normalize one RSS feed. Returns (articles, error_message)."""
    response = None
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
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
                element
                for element in root.iter()
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
                sentiment = (
                    "Positive"
                    if score >= SENTIMENT_POSITIVE_THRESHOLD
                    else "Negative"
                    if score <= SENTIMENT_NEGATIVE_THRESHOLD
                    else "Neutral"
                )
                # Extract entities from title + summary
                entities = extract_entities(f"{title} {summary}")
                # Process language detection and translation
                lang_result = process_article_text(f"{title} {summary}")
                articles.append(
                    {
                        "title": title,
                        "summary": summary[:SUMMARY_MAX_LENGTH]
                        + ("..." if len(summary) > SUMMARY_MAX_LENGTH else ""),
                        "link": link,
                        "sentiment": sentiment,
                        "compound": score,
                        "source": source,
                        "pubDate": pub_date,
                        "category": classify_article(title, summary, is_crypto),
                        "entities": entities,
                        "language": lang_result["language"],
                        "translated_text": lang_result["translated_text"] if lang_result["was_translated"] else "",
                        "was_translated": lang_result["was_translated"],
                    }
                )

            if not articles:
                return [], f"{source} returned no readable articles."
            else:
                return articles, ""
        except requests.RequestException as error:
            last_error = error
            if attempt < MAX_RETRIES - 1:
                delay = BASE_RETRY_DELAY * (2**attempt)
                time.sleep(delay)
            continue
        except (ElementTree.ParseError, UnicodeError) as error:
            return [], f"{source} returned invalid RSS data: {error}"
        finally:
            if response is not None:
                response.close()

    return [], f"{source} could not be loaded after {MAX_RETRIES} attempts: {last_error}"


def export_feeds_to_opml(feeds: dict[str, list[FeedTuple]]) -> str:
    """Export feeds configuration to OPML format."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        '  <head>',
        '    <title>News Pulse Feeds</title>',
        f'    <dateCreated>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")}</dateCreated>',
        '  </head>',
        '  <body>',
    ]

    for category, feed_list in feeds.items():
        lines.append(f'    <outline text="{category}" title="{category}">')
        for feed in feed_list:
            url = feed[0]
            source = feed[1]
            feed_type = feed[3] if len(feed) > 3 else "rss"
            if feed_type == "reddit" or feed_type == "hackernews":
                outline_type = "rss"
            else:
                outline_type = "rss"
            lines.append(
                f'      <outline type="{outline_type}" text="{source}" title="{source}" '
                f'xmlUrl="{url}" htmlUrl="{url}" category="{category}" />'
            )
        lines.append('    </outline>')

    lines.extend(['  </body>', '</opml>'])
    return "\n".join(lines)


def import_feeds_from_opml(opml_content: str) -> dict[str, list[FeedTuple]]:
    """Import feeds configuration from OPML format."""
    try:
        root = ElementTree.fromstring(opml_content)
    except ElementTree.ParseError as e:
        raise ValueError(f"Invalid OPML: {e}") from e

    feeds: dict[str, list[FeedTuple]] = {}

    body = root.find("body")
    if body is None:
        return feeds

    for outline in body.findall(".//outline"):
        # Check if this is a category (has children) or a feed
        children = list(outline)
        if children:
            # This is a category
            category = outline.get("text") or outline.get("title") or "Uncategorized"
            feeds[category] = []
            for child in children:
                url = child.get("xmlUrl") or child.get("htmlUrl")
                source = child.get("text") or child.get("title") or "Unknown"
                is_crypto = category.lower() == "crypto"
                if url:
                    feeds[category].append((url, source, is_crypto, "rss"))
        else:
            # This is a top-level feed without category
            url = outline.get("xmlUrl") or outline.get("htmlUrl")
            source = outline.get("text") or outline.get("title") or "Unknown"
            category = "Imported"
            is_crypto = False
            if url:
                if category not in feeds:
                    feeds[category] = []
                feeds[category].append((url, source, is_crypto, "rss"))

    return feeds


# Reddit API
REDDIT_HEADERS: dict[str, str] = {
    "User-Agent": "NewsPulse/1.0 (by /u/your_username)",
}


def fetch_reddit_posts(subreddit: str, limit: int = 25) -> tuple[list[ArticleDict], str]:
    """Fetch posts from a Reddit subreddit."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        response = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()

        articles = []
        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            title = post_data.get("title", "")
            if not title:
                continue

            selftext = post_data.get("selftext", "")
            summary = selftext[:SUMMARY_MAX_LENGTH] + ("..." if len(selftext) > SUMMARY_MAX_LENGTH else "")
            link = f"https://reddit.com{post_data.get('permalink', '')}"
            score = post_data.get("score", 0)
            created_utc = post_data.get("created_utc", 0)
            pub_date = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            # Simple sentiment based on upvote ratio
            upvote_ratio = post_data.get("upvote_ratio", 0.5)
            compound = (upvote_ratio - 0.5) * 2  # Scale to -1 to 1
            sentiment = (
                "Positive" if compound >= SENTIMENT_POSITIVE_THRESHOLD
                else "Negative" if compound <= SENTIMENT_NEGATIVE_THRESHOLD
                else "Neutral"
            )

            entities = extract_entities(f"{title} {selftext}")
            lang_result = process_article_text(f"{title} {selftext}")

            articles.append({
                "title": title,
                "summary": summary,
                "link": link,
                "sentiment": sentiment,
                "compound": compound,
                "source": f"Reddit r/{subreddit}",
                "pubDate": pub_date,
                "category": "Social & Community",
                "entities": entities,
                "language": lang_result["language"],
                "translated_text": lang_result["translated_text"] if lang_result["was_translated"] else "",
                "was_translated": lang_result["was_translated"],
            })

        return articles, ""
    except requests.RequestException as e:
        return [], f"Reddit r/{subreddit}: {e}"
    except Exception as e:
        return [], f"Reddit r/{subreddit} error: {e}"


# HackerNews API
HN_BASE_URL: str = "https://hacker-news.firebaseio.com/v0"


def fetch_hackernews_stories(story_type: str = "top", limit: int = 25) -> tuple[list[ArticleDict], str]:
    """Fetch stories from HackerNews API."""
    try:
        # Get story IDs
        ids_url = f"{HN_BASE_URL}/{story_type}stories.json"
        ids_response = requests.get(ids_url, timeout=10)
        ids_response.raise_for_status()
        story_ids = ids_response.json()[:limit]

        articles = []
        for story_id in story_ids:
            story_url = f"{HN_BASE_URL}/item/{story_id}.json"
            story_response = requests.get(story_url, timeout=10)
            if story_response.status_code != 200:
                continue
            story = story_response.json()

            title = story.get("title", "")
            if not title:
                continue

            url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")
            score = story.get("score", 0)
            by = story.get("by", "unknown")
            time_ts = story.get("time", 0)
            pub_date = datetime.fromtimestamp(time_ts, tz=timezone.utc).isoformat()

            # Sentiment based on score (logarithmic scale)
            compound = math.tanh(score / 100)  # Scales to -1 to 1
            sentiment = (
                "Positive" if compound >= SENTIMENT_POSITIVE_THRESHOLD
                else "Negative" if compound <= SENTIMENT_NEGATIVE_THRESHOLD
                else "Neutral"
            )

            entities = extract_entities(title)
            lang_result = process_article_text(title)

            articles.append({
                "title": title,
                "summary": f"By {by} · {score} points on HackerNews",
                "link": url,
                "sentiment": sentiment,
                "compound": compound,
                "source": "HackerNews",
                "pubDate": pub_date,
                "category": "Technology & IT",
                "entities": entities,
                "language": lang_result["language"],
                "translated_text": lang_result["translated_text"] if lang_result["was_translated"] else "",
                "was_translated": lang_result["was_translated"],
            })

        return articles, ""
    except requests.RequestException as e:
        return [], f"HackerNews: {e}"
    except Exception as e:
        return [], f"HackerNews error: {e}"

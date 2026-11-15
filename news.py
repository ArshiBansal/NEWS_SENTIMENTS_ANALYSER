from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from news_data import (
    deduplicate_articles,
    export_feeds_to_opml,
    fetch_feed,
    fetch_hackernews_stories,
    fetch_reddit_posts,
    get_relative_time,
    import_feeds_from_opml,
    parse_published_date,
)

FeedTuple = tuple[str, str, bool, str]  # url, source, is_crypto, feed_type


@st.cache_data
def load_feeds() -> dict[str, list[FeedTuple]]:
    """Load feed configuration from feeds.yaml."""
    feeds_path = Path(__file__).parent / "feeds.yaml"
    with feeds_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    feeds: dict[str, list[FeedTuple]] = {}
    for category, feed_list in config.get("feeds", {}).items():
        feeds[category] = []
        for feed in feed_list:
            url = feed["url"]
            source = feed["source"]
            is_crypto = feed["is_crypto"]
            # Determine feed type from URL prefix
            if url.startswith("reddit:"):
                feed_type = "reddit"
            elif url.startswith("hackernews:"):
                feed_type = "hackernews"
            else:
                feed_type = "rss"
            feeds[category].append((url, source, is_crypto, feed_type))
    return feeds


FEEDS: dict[str, list[FeedTuple]] = load_feeds()

st.set_page_config(page_title="News Pulse", page_icon="📰", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    * { font-family: 'Inter', system-ui, sans-serif; }
    .stApp { background: linear-gradient(135deg, #0f0f1e 0%, #141428 100%); color: #e0e0ff; }
    .main-title {
        text-align: center; font-size: clamp(2.5rem, 7vw, 4.2rem); font-weight: 800;
        background: linear-gradient(90deg, #00ff88, #00d4ff, #7c3aed);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin: 1.2rem 0 0;
    }
    .subtitle { text-align: center; color: #a0a0cc; margin: 0 0 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<h1 class="main-title">News Pulse</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Crypto and stock headlines with a quick, '
    'explainable sentiment estimate</p>',
    unsafe_allow_html=True,
)

# Keyboard shortcuts
st.markdown(
    """
    <script>
    // Track focused article index
    let focusedIndex = -1;
    // Streamlit containers with border=True have data-testid="stContainer"
    // Articles have subheader (h3) inside
    const ARTICLE_SELECTOR = '[data-testid="stContainer"]:has(h3), [data-testid="stVerticalBlock"]:has(h3)';

    function getArticles() {
        return Array.from(document.querySelectorAll(ARTICLE_SELECTOR));
    }

    function focusArticle(index) {
        const articles = getArticles();
        if (articles.length === 0) return;

        // Remove previous focus
        articles.forEach((a, i) => {
            a.style.outline = '';
            a.style.boxShadow = '';
            if (i === focusedIndex) {
                a.removeAttribute('data-focused');
            }
        });

        focusedIndex = Math.max(0, Math.min(index, articles.length - 1));
        const article = articles[focusedIndex];
        article.style.outline = '2px solid #00d4ff';
        article.style.boxShadow = '0 0 12px rgba(0, 212, 255, 0.3)';
        article.setAttribute('data-focused', 'true');
        article.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function openFocusedArticle() {
        const articles = getArticles();
        if (focusedIndex >= 0 && focusedIndex < articles.length) {
            // st.link_button renders as <a> tag with role="button"
            const linkBtn = articles[focusedIndex].querySelector('a[role="button"], button[kind="secondary"]');
            if (linkBtn) linkBtn.click();
        }
    }

    const shortcuts = {
        'j': () => focusArticle(focusedIndex + 1),
        'k': () => focusArticle(focusedIndex - 1),
        '/': () => {
            const searchInput = document.querySelector('input[placeholder*="bitcoin" i]');
            if (searchInput) searchInput.focus();
        },
        'o': () => openFocusedArticle(),
        'r': () => {
            const refreshBtn = Array.from(document.querySelectorAll('button')).find(
                b => b.textContent.includes('Refresh')
            );
            if (refreshBtn) refreshBtn.click();
        },
        '?': () => {
            const helpBtn = Array.from(document.querySelectorAll('button')).find(
                b => b.textContent.includes('⌨️') || b.textContent.includes('Shortcuts')
            );
            if (helpBtn) helpBtn.click();
        },
    };

    document.addEventListener('keydown', (e) => {
        // Ignore if typing in input/textarea (except / for search)
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
            if (e.key !== '/') return;
        }
        const handler = shortcuts[e.key.toLowerCase()];
        if (handler) {
            e.preventDefault();
            handler();
        }
    });

    // Initialize: focus first article on load
    setTimeout(() => focusArticle(0), 500);
    </script>
    """,
    unsafe_allow_html=True,
)


ArticleDict = dict[str, Any]

# VADER sentiment thresholds
SENTIMENT_POSITIVE_THRESHOLD: float = 0.1
SENTIMENT_NEGATIVE_THRESHOLD: float = -0.1
SENTIMENT_MOOD_POSITIVE: float = 0.05
SENTIMENT_MOOD_NEGATIVE: float = -0.05


@st.cache_data(ttl=900)
def cached_fetch_feed(url: str, source: str, is_crypto: bool) -> tuple[list[ArticleDict], str]:
    return fetch_feed(url, source, is_crypto)


def build_csv(articles: list[ArticleDict]) -> bytes:
    output = io.StringIO(newline="")
    columns = ["title", "summary", "link", "source", "category", "sentiment", "compound", "pubDate"]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(articles)
    return output.getvalue().encode("utf-8-sig")


# Column customization (in sidebar)
if "selected_columns" not in st.session_state:
    st.session_state.selected_columns = ["sentiment", "source", "category"]

with st.sidebar:
    st.title("News Pulse")
    news_type = st.selectbox("News type", ["All news", "Crypto news", "Stock news"])
    search_query = st.text_input("Search headlines", placeholder="bitcoin, Tesla, ETF...")
    sort_option = st.selectbox(
        "Sort by",
        ["Newest first", "Most positive sentiment", "Most negative sentiment"],
    )
    timeframe = st.selectbox("Published", ["Any time", "Past 24 hours", "Past 7 days"])

    refresh = st.button("Refresh feeds now", use_container_width=True)
    st.caption("Feed results are cached for 15 minutes.")

    with st.expander("⌨️ Keyboard Shortcuts"):
        st.markdown("""
        | Key | Action |
        |-----|--------|
        | `j` / `k` | Navigate articles (next/prev) |
        | `/` | Focus search |
        | `o` | Open selected article |
        | `r` | Refresh feeds |
        | `?` | Show this help |
        """)

    # Column customization
    all_columns = ["sentiment", "compound", "source", "category", "pubDate", "entities"]
    st.session_state.selected_columns = st.multiselect(
        "Displayed columns",
        all_columns,
        default=st.session_state.selected_columns,
        help="Choose which metadata columns to show for each article",
    )

    # Load more / infinite scroll
    if "articles_per_category" not in st.session_state:
        st.session_state.articles_per_category = 20
    if st.button("Load more articles", use_container_width=True):
        st.session_state.articles_per_category += 20
        st.rerun()
    st.caption(f"Showing up to {st.session_state.articles_per_category} articles per category")

    # OPML Import/Export
    with st.expander("📥📤 OPML Import/Export"):
        # Export
        opml_content = export_feeds_to_opml(FEEDS)
        st.download_button(
            "Export feeds as OPML",
            data=opml_content,
            file_name="news-pulse-feeds.opml",
            mime="text/x-opml",
            use_container_width=True,
        )

        # Import
        uploaded_opml = st.file_uploader(
            "Import feeds from OPML",
            type=["opml", "xml"],
            help="Upload an OPML file to replace current feed configuration",
        )
        if uploaded_opml:
            try:
                imported_feeds = import_feeds_from_opml(uploaded_opml.read().decode("utf-8"))
                if imported_feeds:
                    # Save to feeds.yaml
                    feeds_path = Path(__file__).parent / "feeds.yaml"
                    yaml_content: dict[str, Any] = {"feeds": {}}
                    for cat, feed_list in imported_feeds.items():
                        yaml_content["feeds"][cat] = [
                            {"url": url, "source": src, "is_crypto": crypto}
                            for url, src, crypto, _feed_type in feed_list
                        ]
                    with feeds_path.open("w", encoding="utf-8") as f:
                        yaml.dump(yaml_content, f, default_flow_style=False)
                    load_feeds.clear()  # type: ignore[attr-defined]
                    st.success(f"Imported {sum(len(v) for v in imported_feeds.values())} feeds!")
                    st.rerun()
                else:
                    st.warning("No valid feeds found in OPML file.")
            except Exception as e:
                st.error(f"Failed to import OPML: {e}")

    # Feed Health Dashboard
    with st.expander("📊 Feed Health"):
        if "feed_health" not in st.session_state:
            st.session_state.feed_health = {}

        for source in st.session_state.feed_health:
            health = st.session_state.feed_health[source]
            total = health.get("total", 0)
            successes = health.get("successes", 0)
            errors = health.get("errors", 0)
            uptime = (successes / total * 100) if total > 0 else 0
            avg_latency = health.get("total_latency", 0) / successes if successes > 0 else 0

            col1, col2 = st.columns([3, 1])
            col1.write(f"**{source}**")
            col1.caption(f"Uptime: {uptime:.1f}% · Avg latency: {avg_latency:.0f}ms · Errors: {errors}")

        if not st.session_state.feed_health:
            st.caption("Feed health data will appear after loading feeds.")

    # Custom RSS/Atom Feed Input
    with st.expander("➕ Add Custom Feed"):
        custom_url = st.text_input(
            "Feed URL",
            placeholder="https://example.com/feed.xml",
            help="Enter an RSS or Atom feed URL",
        )
        custom_source = st.text_input(
            "Source name",
            placeholder="My Custom Feed",
            help="Display name for this feed",
        )
        custom_is_crypto = st.checkbox("Crypto feed", help="Enable crypto-specific categorization")
        if st.button("Add feed", use_container_width=True, disabled=not (custom_url and custom_source)):
            if custom_url and custom_source:
                # Add to session state for this session
                if "custom_feeds" not in st.session_state:
                    st.session_state.custom_feeds = []
                st.session_state.custom_feeds.append((custom_url, custom_source, custom_is_crypto, "rss"))
                st.success(f"Added '{custom_source}' to current session!")
                st.rerun()

if refresh:
    cached_fetch_feed.clear()  # type: ignore[attr-defined]
    st.rerun()

# Track feeds to retry individually
if "retry_feeds" not in st.session_state:
    st.session_state.retry_feeds = set()

selected_feeds: list[FeedTuple]
if news_type == "Crypto news":
    selected_feeds = FEEDS["Crypto"]
elif news_type == "Stock news":
    selected_feeds = FEEDS["Stocks"]
else:
    selected_feeds = FEEDS["Crypto"] + FEEDS["Stocks"]

# Add custom feeds
if "custom_feeds" in st.session_state and st.session_state.custom_feeds:
    custom_crypto = [f for f in st.session_state.custom_feeds if f[2]]
    custom_stocks = [f for f in st.session_state.custom_feeds if not f[2]]
    if news_type == "Crypto news":
        selected_feeds = [f for f in selected_feeds if f[2]] + custom_crypto
    elif news_type == "Stock news":
        selected_feeds = [f for f in selected_feeds if not f[2]] + custom_stocks
    else:
        selected_feeds = selected_feeds + st.session_state.custom_feeds

articles: list[ArticleDict] = []
feed_errors: list[str] = []
feed_error_map: dict[str, str] = {}  # source -> error message
feed_url_map: dict[str, tuple[str, bool]] = {}  # source -> (url, is_crypto)

with st.spinner("Loading headlines..."):
    for url, source, is_crypto, feed_type in selected_feeds:
        feed_url_map[source] = (url, is_crypto)
        # Check if this feed was requested to retry
        if source in st.session_state.retry_feeds:
            cached_fetch_feed.clear()  # type: ignore[attr-defined]
            st.session_state.retry_feeds.discard(source)

        # Initialize health tracking
        if "feed_health" not in st.session_state:
            st.session_state.feed_health = {}
        if source not in st.session_state.feed_health:
            st.session_state.feed_health[source] = {
                "total": 0,
                "successes": 0,
                "errors": 0,
                "total_latency": 0.0,
            }

        import time
        start_time = time.time()
        
        # Fetch based on feed type
        if feed_type == "reddit":
            # Extract subreddit from URL (e.g., "reddit:cryptocurrency")
            subreddit = url.split(":", 1)[1] if ":" in url else url
            feed_articles, error = fetch_reddit_posts(subreddit)
        elif feed_type == "hackernews":
            # Extract story type from URL (e.g., "hackernews:top")
            story_type = url.split(":", 1)[1] if ":" in url else "top"
            feed_articles, error = fetch_hackernews_stories(story_type)
        else:
            feed_articles, error = cached_fetch_feed(url, source, is_crypto)
        
        latency_ms = (time.time() - start_time) * 1000

        # Update health metrics
        health = st.session_state.feed_health[source]
        health["total"] += 1
        health["total_latency"] += latency_ms
        if error:
            health["errors"] += 1
        else:
            health["successes"] += 1

        articles.extend(feed_articles)
        if error:
            feed_errors.append(error)
            feed_error_map[source] = error

# Deduplicate articles using fuzzy matching
deduplicated = deduplicate_articles(articles)

if feed_errors:
    for error in feed_errors:
        st.warning(error)

with st.expander("Feed status"):
    for _url, source, _is_crypto, _feed_type in selected_feeds:
        col1, col2 = st.columns([4, 1])
        source_error = feed_error_map.get(source, "")
        if source_error:
            col1.error(source_error)
            if col2.button("Retry", key=f"retry_{source}", use_container_width=True):
                st.session_state.retry_feeds.add(source)
                st.rerun()
        else:
            source_count = sum(article["source"] == source for article in articles)
            col1.success(f"{source}: {source_count} article(s) loaded")

categories: list[str] = sorted({article["category"] for article in deduplicated})
sources: list[str] = sorted({article["source"] for article in deduplicated})
with st.sidebar:
    selected_categories = st.multiselect("Categories", categories, default=categories)
    selected_sentiments = st.multiselect(
        "Sentiment",
        ["Positive", "Neutral", "Negative"],
        default=["Positive", "Neutral", "Negative"],
    )
    selected_sources = st.multiselect("Sources", sources, default=sources)
    articles_per_category = st.slider(
        "Articles per category",
        1,
        100,
        st.session_state.articles_per_category,
    )
    st.session_state.articles_per_category = articles_per_category

filtered_articles: list[ArticleDict] = []
cutoff: datetime | None = None
if timeframe == "Past 24 hours":
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
elif timeframe == "Past 7 days":
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

query = search_query.strip().casefold()
for article in deduplicated:
    searchable_text = " ".join(
        (article["title"], article["summary"], article["source"], article["category"])
    ).casefold()
    published = parse_published_date(article["pubDate"])
    if query and query not in searchable_text:
        continue
    if article["category"] not in selected_categories:
        continue
    if article["sentiment"] not in selected_sentiments:
        continue
    if article["source"] not in selected_sources:
        continue
    if cutoff and (published is None or published < cutoff):
        continue
    filtered_articles.append(article)

if sort_option == "Newest first":
    filtered_articles.sort(
        key=lambda article: (
            parse_published_date(article["pubDate"]) or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
elif sort_option == "Most positive sentiment":
    filtered_articles.sort(key=lambda article: article["compound"], reverse=True)
else:
    filtered_articles.sort(key=lambda article: article["compound"])

scores = [article["compound"] for article in filtered_articles]
average_score = sum(scores) / len(scores) if scores else 0
positive_count = sum(
    score >= SENTIMENT_POSITIVE_THRESHOLD for score in scores
)
negative_count = sum(
    score <= SENTIMENT_NEGATIVE_THRESHOLD for score in scores
)
neutral_count = len(scores) - positive_count - negative_count
mood = (
    "Positive"
    if average_score > SENTIMENT_MOOD_POSITIVE
    else "Negative"
    if average_score < SENTIMENT_MOOD_NEGATIVE
    else "Neutral"
)

metric_columns = st.columns(4)
metric_columns[0].metric("Articles", len(filtered_articles))
metric_columns[1].metric("Average sentiment", f"{average_score:+.2f}")
metric_columns[2].metric("Overall tone", mood)
metric_columns[3].metric("Sources", len({article["source"] for article in filtered_articles}))

chart_column, export_column = st.columns([3, 1])
with chart_column:
    st.caption("Sentiment distribution (VADER compound score thresholds: ±0.10)")
    st.bar_chart(
        {
            "Sentiment": ["Positive", "Neutral", "Negative"],
            "Articles": [positive_count, neutral_count, negative_count],
        },
        x="Sentiment",
        y="Articles",
    )
with export_column:
    st.download_button(
        "Download filtered news as CSV",
        data=build_csv(filtered_articles),
        file_name="news-pulse.csv",
        mime="text/csv",
        disabled=not filtered_articles,
        use_container_width=True,
    )

st.subheader(news_type)
if not filtered_articles:
    if feed_errors and not deduplicated:
        st.error("No feeds could be loaded. Check the source status above and try again later.")
    else:
        st.info("No articles match these filters. Try changing the search or filter selections.")
else:
    st.caption(f"Showing {len(filtered_articles)} filtered article(s).")
    grouped: dict[str, list[ArticleDict]] = defaultdict(list)
    for article in filtered_articles:
        grouped[article["category"]].append(article)

    for category, category_articles in grouped.items():
        st.markdown(f"### {category}")
        if len(category_articles) > articles_per_category:
            st.caption(
                f"Showing {articles_per_category} of "
                f"{len(category_articles)} articles in this category."
            )
        for article in category_articles[:articles_per_category]:
            with st.container(border=True):
                st.subheader(article["title"])
                if article["summary"]:
                    st.write(article["summary"])

                # Build dynamic details based on selected columns
                detail_parts = []
                cols = st.session_state.selected_columns
                if "sentiment" in cols:
                    detail_parts.append(f"{article['sentiment']} ({article['compound']:+.2f})")
                elif "compound" in cols:
                    detail_parts.append(f"Score: {article['compound']:+.2f}")
                if "source" in cols:
                    detail_parts.append(article["source"])
                if "category" in cols:
                    detail_parts.append(article["category"])
                if "pubDate" in cols:
                    detail_parts.append(get_relative_time(article["pubDate"]))
                if "entities" in cols and article.get("entities"):
                    entity_strs = [f"{e['text']} ({e['label']})" for e in article["entities"][:3]]
                    detail_parts.append("Entities: " + ", ".join(entity_strs))
                if "language" in cols and article.get("language"):
                    lang_display = article["language"]
                    if article.get("was_translated"):
                        lang_display += " → EN"
                    detail_parts.append(f"Lang: {lang_display}")
                    if article.get("was_translated") and article.get("translated_text"):
                        with st.expander("🌐 Translation"):
                            st.write(article["translated_text"])

                if detail_parts:
                    st.caption(" · ".join(detail_parts))
                if article["link"]:
                    st.link_button("Open original article", article["link"])

st.divider()
st.caption(
    "Sources: CoinDesk, CoinTelegraph, and Yahoo Finance RSS. "
    "VADER analyzes headline wording and is not a measure of "
    "market performance or investment advice."
)

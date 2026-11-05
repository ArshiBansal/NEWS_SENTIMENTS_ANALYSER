import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import streamlit as st

from news_data import fetch_feed, get_relative_time, parse_published_date


FEEDS = {
    "Crypto": [
        ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk", True),
        ("https://cointelegraph.com/rss", "CoinTelegraph", True),
    ],
    "Stocks": [
        (
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,AAPL,TSLA,MSFT,NVDA,GOOGL,AMZN,META",
            "Yahoo Finance",
            False,
        ),
    ],
}

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
    '<p class="subtitle">Crypto and stock headlines with a quick, explainable sentiment estimate</p>',
    unsafe_allow_html=True,
)


@st.cache_data(ttl=900)
def cached_fetch_feed(url, source, is_crypto):
    return fetch_feed(url, source, is_crypto)


def build_csv(articles):
    output = io.StringIO(newline="")
    columns = ["title", "summary", "link", "source", "category", "sentiment", "compound", "pubDate"]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(articles)
    return output.getvalue().encode("utf-8-sig")


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

if refresh:
    cached_fetch_feed.clear()
    st.rerun()

if news_type == "Crypto news":
    selected_feeds = FEEDS["Crypto"]
elif news_type == "Stock news":
    selected_feeds = FEEDS["Stocks"]
else:
    selected_feeds = FEEDS["Crypto"] + FEEDS["Stocks"]

articles = []
feed_errors = []
with st.spinner("Loading headlines..."):
    for url, source, is_crypto in selected_feeds:
        feed_articles, error = cached_fetch_feed(url, source, is_crypto)
        articles.extend(feed_articles)
        if error:
            feed_errors.append(error)

deduplicated = []
seen_articles = set()
for article in articles:
    key = article["link"].rstrip("/").casefold() or (
        article["source"].casefold(),
        article["title"].strip().casefold(),
    )
    if key not in seen_articles:
        seen_articles.add(key)
        deduplicated.append(article)

if feed_errors:
    for error in feed_errors:
        st.warning(error)

with st.expander("Feed status"):
    for _, source, _ in selected_feeds:
        source_error = next((error for error in feed_errors if error.startswith(source)), "")
        if source_error:
            st.error(source_error)
        else:
            source_count = sum(article["source"] == source for article in articles)
            st.success(f"{source}: {source_count} article(s) loaded")

categories = sorted({article["category"] for article in deduplicated})
sources = sorted({article["source"] for article in deduplicated})
with st.sidebar:
    selected_categories = st.multiselect("Categories", categories, default=categories)
    selected_sentiments = st.multiselect(
        "Sentiment",
        ["Positive", "Neutral", "Negative"],
        default=["Positive", "Neutral", "Negative"],
    )
    selected_sources = st.multiselect("Sources", sources, default=sources)
    articles_per_category = st.slider("Articles per category", 1, 25, 10)

filtered_articles = []
cutoff = None
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
        key=lambda article: parse_published_date(article["pubDate"])
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
elif sort_option == "Most positive sentiment":
    filtered_articles.sort(key=lambda article: article["compound"], reverse=True)
else:
    filtered_articles.sort(key=lambda article: article["compound"])

scores = [article["compound"] for article in filtered_articles]
average_score = sum(scores) / len(scores) if scores else 0
positive_count = sum(score >= 0.1 for score in scores)
negative_count = sum(score <= -0.1 for score in scores)
neutral_count = len(scores) - positive_count - negative_count
mood = (
    "Positive" if average_score > 0.05
    else "Negative" if average_score < -0.05
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
    grouped = defaultdict(list)
    for article in filtered_articles:
        grouped[article["category"]].append(article)

    for category, category_articles in grouped.items():
        st.markdown(f"### {category}")
        if len(category_articles) > articles_per_category:
            st.caption(
                f"Showing {articles_per_category} of {len(category_articles)} articles in this category."
            )
        for article in category_articles[:articles_per_category]:
            with st.container(border=True):
                st.subheader(article["title"])
                if article["summary"]:
                    st.write(article["summary"])
                details = (
                    f"{article['sentiment']} ({article['compound']:+.2f}) · "
                    f"{article['source']} · {get_relative_time(article['pubDate'])}"
                )
                st.caption(details)
                if article["link"]:
                    st.link_button("Open original article", article["link"])

st.divider()
st.caption(
    "Sources: CoinDesk, CoinTelegraph, and Yahoo Finance RSS. "
    "VADER analyzes headline wording and is not a measure of market performance or investment advice."
)

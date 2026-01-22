import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from dateutil import parser
from collections import defaultdict

# ── VADER Sentiment ──────────────────────────────────────────────────────────
analyzer = SentimentIntensityAnalyzer()

# ── Strong headers to avoid 403/blocks on Streamlit Cloud ───────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/',
    'Connection': 'keep-alive',
    'Accept-Encoding': 'gzip, deflate',
}

# ── Page config + Enhanced modern theme ─────────────────────────────────────
st.set_page_config(page_title="News Pulse", page_icon="📰", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    * { font-family: 'Inter', system-ui, sans-serif; }

    .stApp {
        background: linear-gradient(135deg, #0f0f1e 0%, #141428 100%);
        color: #e0e0ff;
        background-attachment: fixed;
    }

    .stApp::before {
        content: "";
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: radial-gradient(circle at 10% 20%, rgba(0,255,136,0.03) 0%, transparent 50%),
                    radial-gradient(circle at 90% 80%, rgba(0,212,255,0.03) 0%, transparent 50%);
        pointer-events: none;
        z-index: -1;
    }

    .main-header {
        font-size: 4.2rem;
        font-weight: 800;
        text-align: center;
        background: linear-gradient(90deg, #00ff88, #00d4ff, #7c3aed, #ff00aa);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: gradientFlow 8s linear infinite;
        margin: 1.5rem 0 0.5rem;
        text-shadow: 0 0 20px rgba(0,255,136,0.4);
    }

    @keyframes gradientFlow {
        0% { background-position: 0% 50%; }
        100% { background-position: 200% 50%; }
    }

    .subtitle { text-align: center; color: #a0a0ff; font-size: 1.25rem; margin-top: -0.8rem; margin-bottom: 2rem; font-weight: 400; }

    .news-card {
        background: rgba(26, 26, 46, 0.75);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(0, 255, 136, 0.18);
        border-radius: 16px;
        padding: 1.4rem;
        margin: 0.8rem 0;
        transition: all 0.35s cubic-bezier(0.165, 0.84, 0.44, 1);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
        opacity: 0;
        transform: translateY(20px);
        animation: cardFadeIn 0.6s forwards;
        display: flex;
        flex-direction: column;
        height: 100%;
    }

    @keyframes cardFadeIn { to { opacity: 1; transform: translateY(0); } }

    .news-card:hover {
        transform: translateY(-8px) scale(1.015);
        border-color: #00d4ff;
        box-shadow: 0 16px 48px rgba(0, 212, 255, 0.18);
    }

    .news-title { margin: 0 0 0.8rem; font-size: 1.28rem; font-weight: 700; line-height: 1.4; }
    .news-title a { color: #e0e0ff; text-decoration: none; transition: color 0.3s; }
    .news-title a:hover { color: #00ff88; }

    .news-summary { color: #c0c0ff; font-size: 0.98rem; line-height: 1.55; margin: 0.6rem 0 1rem; flex-grow: 1; }

    .meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.9rem; color: #9090cc; flex-wrap: wrap; gap: 10px; }

    .sentiment-badge { padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 0.85rem; }
    .sentiment-pos { background: rgba(0,255,136,0.15); color: #00ff88; }
    .sentiment-neg  { background: rgba(255,77,148,0.15); color: #ff4d94; }
    .sentiment-neu  { background: rgba(136,136,136,0.15); color: #aaa; }

    .source { color: #00d4ff; font-weight: 500; }
    .time-ago { font-style: italic; color: #a0a0cc; }

    .mood-bar { background: #1a1a2e; border-radius: 12px; padding: 16px; margin: 1.5rem 0; text-align: center; border: 1px solid rgba(0,255,136,0.2); }
    .mood-positive { color: #00ff88; font-weight: 700; font-size: 1.5rem; }
    .mood-negative { color: #ff4d94; font-weight: 700; font-size: 1.5rem; }
    .mood-neutral  { color: #a0a0ff; font-weight: 700; font-size: 1.5rem; }

    .category-header { font-size: 1.9rem; font-weight: 700; color: #00ff88; margin: 2.5rem 0 1.2rem; padding-bottom: 0.6rem; border-bottom: 2px solid rgba(0,255,136,0.35); }
    .category-note { font-size: 0.95rem; color: #a0a0cc; margin: -0.8rem 0 1.4rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-header">News Pulse</h1>', unsafe_allow_html=True)
st.markdown(
    "<p class='subtitle'>Live Crypto & Stock News • Real-time Sentiment Analysis</p>",
    unsafe_allow_html=True
)

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.title("News Pulse")
    st.markdown("---")

    news_type = st.radio("News Type", ["Crypto News", "Stock News"], index=0)

    search_query = st.text_input("🔍 Filter news", placeholder="bitcoin, tesla, ETF...", key="search")
    search_query = search_query.strip().lower()

    sort_option = st.selectbox(
        "Sort by",
        ["Newest first", "Most positive sentiment", "Most negative sentiment"],
        index=0
    )

    if st.button("Refresh News", use_container_width=True):
        st.rerun()

    st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")

# ── Helper function for relative time ────────────────────────────────────────
def get_relative_time(pub_date_str):
    if not pub_date_str:
        return "Date unknown"
    try:
        dt = parser.parse(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt

        if delta.days > 7:
            return dt.strftime("%d %b %Y")
        elif delta.days > 1:
            return f"{delta.days} days ago"
        elif delta.days == 1:
            return "Yesterday"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} min{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"
    except:
        return "Date unknown"

# ── Category classifier ──────────────────────────────────────────────────────
def classify_article(title, summary, is_crypto):
    text = (title + " " + summary).lower()
    if is_crypto:
        if any(k in text for k in ["bitcoin", "btc"]): return "Bitcoin & Major Coins"
        if any(k in text for k in ["defi", "uniswap", "aave", "stablecoin", "usdt", "usdc"]): return "DeFi & Stablecoins"
        if any(k in text for k in ["sec", "regulation", "etf", "cftc", "ban", "tax", "policy"]): return "Regulation & Policy"
        if any(k in text for k in ["nft", "gaming", "metaverse"]): return "NFTs & Gaming"
        return "Markets & Trading"
    else:
        if any(k in text for k in ["apple", "microsoft", "nvidia", "google", "meta", "tech", "ai"]): return "Technology & IT"
        if any(k in text for k in ["earning", "earnings", "quarter", "revenue", "profit"]): return "Earnings & Companies"
        if any(k in text for k in ["fed", "inflation", "rate", "gdp", "jobs", "economy"]): return "Macro & Economy"
        if any(k in text for k in ["bank", "jpmorgan", "financial", "goldman"]): return "Financials & Banking"
        return "Markets & Indices"

# ── RSS fetch functions with debug logging for Streamlit Cloud ──────────────
@st.cache_data(ttl=900)
def get_crypto_news():
    sources = [
        ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
        ("https://cointelegraph.com/rss", "CoinTelegraph")
    ]
    articles = []
    for url, src in sources:
        try:
            r = requests.get(url, timeout=20, headers=HEADERS)
            st.write(f"Debug: {src} → Status: {r.status_code}")
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'xml')
                items = soup.find_all('item')
                st.write(f"Debug: {src} → Found {len(items)} items")
                for item in items[:40]:
                    title = item.find('title')
                    desc = item.find('description')
                    link = item.find('link')
                    pubdate = item.find('pubDate')

                    title_text = title.text.strip() if title else ''
                    desc_text = desc.text.strip() if desc else ''
                    link_text = link.text.strip() if link else ''

                    if not title_text: continue

                    vs = analyzer.polarity_scores(title_text + " " + desc_text)
                    score = vs['compound']
                    sentiment = "Positive" if score >= 0.1 else "Negative" if score <= -0.1 else "Neutral"
                    cls = f"sentiment-{sentiment.lower()[:3]}"

                    pub_date_str = pubdate.text if pubdate else ""

                    category = classify_article(title_text, desc_text, True)

                    articles.append({
                        "title": title_text,
                        "summary": desc_text[:280] + "..." if len(desc_text) > 280 else desc_text,
                        "link": link_text,
                        "sentiment": sentiment,
                        "cls": cls,
                        "source": src,
                        "compound": score,
                        "pubDate": pub_date_str,
                        "category": category
                    })
            else:
                st.write(f"Debug: {src} → Failed with status {r.status_code}")
        except Exception as e:
            st.write(f"Debug: {src} → Error: {str(e)}")
    return articles

@st.cache_data(ttl=900)
def get_stock_news():
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,AAPL,TSLA,MSFT,NVDA,GOOGL,AMZN,META"
    articles = []
    try:
        r = requests.get(url, timeout=20, headers=HEADERS)
        st.write(f"Debug: Yahoo Finance → Status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, 'xml')
            items = soup.find_all('item')
            st.write(f"Debug: Yahoo Finance → Found {len(items)} items")
            for item in items[:40]:
                title = item.find('title')
                desc = item.find('description')
                link = item.find('link')
                pubdate = item.find('pubDate')

                title_text = title.text.strip() if title else ''
                desc_text = desc.text.strip() if desc else ''
                link_text = link.text.strip() if link else ''

                if not title_text: continue

                vs = analyzer.polarity_scores(title_text + " " + desc_text)
                score = vs['compound']
                sentiment = "Positive" if score >= 0.1 else "Negative" if score <= -0.1 else "Neutral"
                cls = f"sentiment-{sentiment.lower()[:3]}"

                pub_date_str = pubdate.text if pubdate else ""

                category = classify_article(title_text, desc_text, False)

                articles.append({
                    "title": title_text,
                    "summary": desc_text[:280] + "..." if len(desc_text) > 280 else desc_text,
                    "link": link_text,
                    "sentiment": sentiment,
                    "cls": cls,
                    "source": "Yahoo Finance",
                    "compound": score,
                    "pubDate": pub_date_str,
                    "category": category
                })
        else:
            st.write(f"Debug: Yahoo Finance → Failed with status {r.status_code}")
    except Exception as e:
        st.write(f"Debug: Yahoo Finance → Error: {str(e)}")
    return articles

# ── Load news ────────────────────────────────────────────────────────────────
with st.spinner("Loading latest news..."):
    if news_type == "Crypto News":
        news_articles = get_crypto_news()
    else:
        news_articles = get_stock_news()

# ── Apply search filter ──────────────────────────────────────────────────────
if search_query:
    news_articles = [
        art for art in news_articles
        if search_query in (art["title"] + " " + art["summary"]).lower()
    ]

# ── Sorting ──────────────────────────────────────────────────────────────────
def get_sort_key(article):
    if sort_option == "Newest first":
        try:
            return parser.parse(article["pubDate"]) if article["pubDate"] else datetime.min
        except:
            return datetime.min
    elif sort_option == "Most positive sentiment":
        return article["compound"]
    elif sort_option == "Most negative sentiment":
        return -article["compound"]
    return 0

news_articles.sort(key=get_sort_key, reverse=True)

# ── Group by category ────────────────────────────────────────────────────────
grouped = defaultdict(list)
for art in news_articles:
    grouped[art["category"]].append(art)

# ── Market Mood ──────────────────────────────────────────────────────────────
scores = [art['compound'] for art in news_articles if 'compound' in art]
avg_score = sum(scores) / len(scores) if scores else 0

if avg_score > 0.05:
    mood_class = "mood-positive"
    mood_text = f"Bullish ({round(avg_score * 100, 1)}%)"
elif avg_score < -0.05:
    mood_class = "mood-negative"
    mood_text = f"Bearish ({round(-avg_score * 100, 1)}%)"
else:
    mood_class = "mood-neutral"
    mood_text = f"Neutral ({round(avg_score * 100, 1)}%)"

st.markdown(f"""
<div class="mood-bar">
    <div style="font-size:1.5rem; margin-bottom:8px;">Market Mood</div>
    <div class="{mood_class}" style="font-size:2.1rem;">{mood_text}</div>
</div>
""", unsafe_allow_html=True)

# ── Display grouped by category ──────────────────────────────────────────────
st.subheader(news_type)

if not news_articles:
    st.info("No news articles loaded right now.\n\nThis is usually caused by RSS feeds blocking requests from cloud platforms like Streamlit Cloud.\n\nTry:\n1. Refreshing the page\n2. Switching news type\n3. Running locally to test\n\nCheck the app logs for debug messages (status codes / errors).")
else:
    st.success(f"Total articles loaded: {len(news_articles)}")

    for category, articles in grouped.items():
        if len(articles) == 0:
            continue

        st.markdown(f'<div class="category-header">{category}</div>', unsafe_allow_html=True)

        display_articles = articles[:10]
        count = len(display_articles)

        st.markdown(f'<div class="category-note">Showing {count} article{"s" if count != 1 else ""}</div>', unsafe_allow_html=True)

        for i, art in enumerate(display_articles):
            time_ago = get_relative_time(art["pubDate"])

            st.markdown(f"""
            <div class="news-card" style="animation-delay: {i*0.08}s;">
                <p class="news-title">
                    <a href="{art['link']}" target="_blank">{art['title']}</a>
                </p>
                <p class="news-summary">{art['summary']}</p>
                <div class="meta">
                    <span class="sentiment-badge {art['cls']}">{art['sentiment']}</span>
                    <span class="source">{art['source']}</span>
                    <span class="time-ago">{time_ago}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")
st.caption("Crypto News: CoinDesk + CoinTelegraph RSS | Stock News: Yahoo Finance RSS | Sentiment: VADER")
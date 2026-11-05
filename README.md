<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Space+Grotesk&weight=700&size=38&duration=2800&pause=900&color=00F5A0&center=true&vCenter=true&width=720&height=70&lines=NEWS+PULSE;Headlines+in.+Signals+out." alt="News Pulse — Headlines in. Signals out." />

<br>

**A live market-news radar for curious humans.**
<br>
Crypto + stocks · RSS-powered · sentiment-scored · built with Streamlit

<br><br>

<a href="https://stocksnews.streamlit.app/"><img src="https://img.shields.io/badge/OPEN%20LIVE%20DASHBOARD-00D4FF?style=for-the-badge&logo=streamlit&logoColor=white" alt="Open the live News Pulse dashboard"></a>
&nbsp;
<img src="https://img.shields.io/badge/PYTHON-3.10%2B-FFE66D?style=for-the-badge&logo=python&logoColor=222222" alt="Python 3.10 and newer">
&nbsp;
<img src="https://img.shields.io/badge/NO%20API%20KEYS-FF4FA3?style=for-the-badge&logo=keycdn&logoColor=white" alt="No API keys required">

<br><br>

*The market never sleeps. Your browser tabs probably shouldn't have to either.*

</div>

---

> [!IMPORTANT]
> **This is a news-reading and headline-sentiment tool—not a ~~crystal ball~~ trading system.**
> VADER scores the *language* in headlines. It does not predict prices, understand the full article, or provide investment advice.

## The signal board

| What you can do | What it means in practice |
|:--|:--|
| **Scan all three feeds** | Browse CoinDesk, CoinTelegraph, and Yahoo Finance—together or by market. |
| **Find your angle** | Search, then filter by source, category, sentiment, or time window. |
| **Read the room** | See average headline sentiment, article counts, and a positive / neutral / negative chart. |
| **Sort the noise** | Put the newest, most positive, or most negative headlines first. |
| **Take it with you** | Export the *filtered* articles as CSV. |
| **Keep it fresh** | Feeds are cached for 15 minutes; hit **Refresh feeds now** to fetch again. |
| **Know when a feed flakes** | Check source status and see feed-specific errors in the dashboard. |

<details>
<summary><strong>How to read the sentiment meter</strong></summary>
<br>

VADER returns a compound score from **−1.00** (most negative) to **+1.00** (most positive).

| Compound score | Label |
|:--:|:--|
| `≤ −0.10` | 💗 **Negative** |
| `−0.10 … +0.10` | 💜 **Neutral** |
| `≥ +0.10` | 💚 **Positive** |

The overall tone uses the average of the currently filtered headlines. One headline can be dramatic; a feed-wide average is still just a rough snapshot.

</details>

## A tiny look under the hood

```text
CoinDesk ─────┐
CoinTelegraph ─┼─> RSS / Atom parser ─> deduplicate ─> VADER + categories
Yahoo Finance ┘                                      │
                                                     v
                            search + filters + charts + CSV
```

> *A headline is a signal about what someone wrote—not proof of what the market will do.*

## Run it locally

**Python 3.10+** · Internet connection required for live feeds · No API key or database

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run news.py
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

## Stack, no smoke and mirrors

| Layer | Tool | Job |
|:--|:--|:--|
| Interface | [Streamlit](https://streamlit.io/) | Interactive dashboard and CSV download |
| Feed retrieval | [Requests](https://requests.readthedocs.io/) | Fetch public news feeds |
| Feed parsing | [ElementTree](https://docs.python.org/3/library/xml.etree.elementtree.html) + [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) | Read RSS / Atom and clean summaries |
| Headline scoring | [VADER](https://github.com/cjhutto/vaderSentiment) | Lexicon-based sentiment estimates |
| Dates | [python-dateutil](https://dateutil.readthedocs.io/) | Parse feed publication times |

## Deploy on Streamlit Community Cloud

The repo is already arranged for Community Cloud: root-level `news.py`, `requirements.txt`, and `.streamlit/config.toml`. Select `news.py` as the app entrypoint. **No secrets or `packages.txt` are needed.**

See [DEPLOYMENT.md](./DEPLOYMENT.md) for deployment settings and troubleshooting.

## Honest limitations

- **A feed can go quiet.** Providers control availability and what they publish; one failing source does not mean all sources are down.
- **Sentiment is not financial context.** VADER can miss irony, jargon, and the difference between a company reporting *losses* and a headline saying it *lost* something.
- **Categories are keyword-based.** They are handy filing labels, not a financial analyst in a tiny hat.
- **No price data or forecasts.** This dashboard analyzes headlines; it does not track market prices or recommend trades.
- **Cached means not instantaneous.** Results can be up to 15 minutes old unless manually refreshed.

<h3 align="center">Less doomscroll. More context.</h3>

<p align="center"><sub>Built with Python + Streamlit · Powered by public feeds · <mark>Not financial advice</mark></sub></p>

<p align="center"><a href="https://stocksnews.streamlit.app/"><strong>Launch News Pulse ↗</strong></a></p>

# News Pulse

News Pulse is a Streamlit dashboard for browsing crypto and stock headlines from public RSS feeds. It estimates headline sentiment with VADER; these scores are informational and are not a measure of market performance or investment advice.

## Features

- Browse crypto headlines, stock headlines, or both together.
- Search and filter by source, category, sentiment, and publication date.
- Sort by publication date or VADER sentiment.
- View article counts, average sentiment, and sentiment distribution.
- Export the currently filtered headlines to CSV.
- See feed-level errors when a source is unavailable.
- Cache RSS responses for 15 minutes, with a manual refresh option.

## Run locally

Python 3.10 or later is required. CI tests Python 3.11, 3.12, and 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run news.py
```

The app does not require API keys or a database. It needs an internet connection to retrieve RSS and Atom feeds.

## Run tests

```powershell
python -m unittest discover -s tests
```

## Deploy on Streamlit Community Cloud

Deploy the root-level `news.py` entrypoint from your GitHub repository. Community Cloud installs dependencies from `requirements.txt` and reads the theme in `.streamlit/config.toml`. Select Python 3.12 or 3.13; no secrets or `packages.txt` are required.

See [DEPLOYMENT.md](./DEPLOYMENT.md) for deployment, redeployment, and troubleshooting steps.

## Sources and limitations

- Crypto: CoinDesk and CoinTelegraph RSS
- Stocks: Yahoo Finance RSS
- RSS and Atom feeds are fetched from the providers above; availability and article coverage are controlled by them.
- Sentiment: VADER compound scores, classified as positive at `>= 0.10`, negative at `<= -0.10`, and neutral otherwise

VADER is a general-purpose lexicon-based analyzer and may misread financial context, sarcasm, or headlines that require article-level context.

## Project checks

The GitHub Actions workflow runs the unit tests and Python syntax check on Python 3.11, 3.12, and 3.13 for pushes and pull requests.

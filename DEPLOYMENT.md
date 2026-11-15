# Streamlit Community Cloud deployment

## Repository files

The repository is arranged for Community Cloud:

- Entrypoint: `news.py` at the repository root
- Python dependencies: `requirements.txt` at the repository root
- Feed configuration: `feeds.yaml` at the repository root
- Streamlit configuration: `.streamlit/config.toml`
- No `packages.txt` is needed; the app has no OS-level dependencies.
- No Streamlit secrets are needed; the app uses public feeds and no API keys.

Keep the entrypoint, dependency file, `feeds.yaml`, and `.streamlit` directory committed to the branch used for deployment.

## Deploy or redeploy

1. Push the changes to the GitHub branch connected to the app.
2. In Streamlit Community Cloud, create or open the app and select the repository, deployed branch, and `news.py` as the entrypoint.
3. For a new deployment, select Python 3.12 or 3.13 in Advanced settings. Python 3.12 is the Community Cloud default; both versions are covered by CI.
4. Deploy and check the app's Cloud logs if startup fails.

Community Cloud installs the packages listed in the root `requirements.txt`. Dependency changes can take a few minutes to install. The Python version is chosen in the Cloud deployment settings; changing it after deployment requires deleting and redeploying the app.

## After deployment

- Confirm the dashboard loads and inspect the **Feed status** panel. RSS providers can be unavailable independently of the app.
- Use **Refresh feeds now** to bypass the app's 15-minute feed cache.
- Check Community Cloud logs for startup errors; feed-specific request and parsing errors are shown in the app.
- Keep secrets out of the repository. If a future feature needs credentials, add them through Community Cloud's Secrets settings and read them with `st.secrets`.

## spaCy model

The app uses the `en_core_web_sm` spaCy model for named entity recognition. This model is downloaded at runtime on first use (lazy loading). On Community Cloud, the first request may take longer while the model downloads. To pre-install the model, add a `packages.txt` with:

```
python3-spacy
```

And modify `requirements.txt` to include `spacy` (already present). Alternatively, the model will auto-download on first use.

## Feed configuration

Feed sources are defined in `feeds.yaml` at the repository root. To add or modify feeds:

1. Edit `feeds.yaml` locally
2. Commit and push to the deployed branch
3. The app will pick up changes on next refresh (or restart)

The `feeds.yaml` structure supports:
- **RSS/Atom feeds**: Standard `url`, `source`, `is_crypto` fields
- **Reddit subreddits**: Use `url: "reddit:subreddit_name"` format
- **HackerNews**: Use `url: "hackernews:top"` or `url: "hackernews:new"` format

## Reddit API rate limits

The app uses Reddit's public JSON API without authentication (User-Agent only). This provides ~60 requests/minute. For production deployments with higher traffic, add Reddit API credentials to Streamlit secrets:

```toml
# .streamlit/secrets.toml (do not commit)
REDDIT_CLIENT_ID = "your_client_id"
REDDIT_CLIENT_SECRET = "your_client_secret"
REDDIT_USER_AGENT = "NewsPulse/1.0"
```

Then modify `news_data.py` to use these credentials for authenticated requests.

## Translation API

The app uses `deep-translator` with Google Translate (free, no API key). For production use with higher reliability, consider adding a paid translation API key (DeepL, Google Cloud Translation) to Streamlit secrets.

## CI/CD

GitHub Actions (`.github/workflows/tests.yml`) runs on every push and pull request:
- Unit tests (11 tests)
- UI tests (2 tests with Streamlit AppTest)
- Ruff linting
- Black formatting check
- MyPy strict type checking
- Python syntax validation

All checks must pass before merging to the deployment branch.

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| App fails to start | Check Cloud logs for import errors; verify `requirements.txt` matches `pyproject.toml` |
| Feed shows error | Check **Feed status** panel; source may be temporarily unavailable |
| spaCy model missing | First load triggers download; wait or pre-install via `packages.txt` |
| Reddit rate limited | Add authenticated credentials to secrets |
| Translation fails | Google Translate free tier has limits; consider paid API |

See the [Streamlit Community Cloud deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app) and [dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) for platform details.
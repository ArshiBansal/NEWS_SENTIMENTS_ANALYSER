# Streamlit Community Cloud deployment

## Repository files

The repository is arranged for Community Cloud:

- Entrypoint: `news.py` at the repository root
- Python dependencies: `requirements.txt` at the repository root
- Streamlit configuration: `.streamlit/config.toml`
- No `packages.txt` is needed; the app has no OS-level dependencies.
- No Streamlit secrets are needed; the app uses public feeds and no API keys.

Keep the entrypoint, dependency file, and `.streamlit` directory committed to the branch used for deployment.

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

See the [Streamlit Community Cloud deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app) and [dependency guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) for platform details.

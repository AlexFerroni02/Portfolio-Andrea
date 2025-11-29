// ...existing code...
# 📈 Portfolio Cloud Manager

A self-hosted, professional portfolio tracker built with **Python** and **Streamlit**.
It uses **Google Sheets** as a persistent database and **Yahoo Finance** for pricing.

Key features
- ☁️ Cloud persistence on Google Sheets
- 💰 Tracks invested capital vs market value (including fees)
- 📊 Interactive charts (pie, historical, drill-down)
- 🚀 DEGIRO CSV importer (Transactions.csv)
- 🤖 Manual ISIN → ticker mapping (e.g., `SWDA.MI`)

---

## 1. Prerequisites — Google Cloud & Google Sheets

Before running the app you must configure Google Cloud and a Google Sheet used as the database.

A. Google Cloud
1. Open https://console.cloud.google.com/ and create a new project (e.g., `PortfolioApp`).
2. Enable APIs:
   - Google Sheets API
   - Google Drive API
3. Create a Service Account: APIs & Services → Credentials → Create Service Account (e.g., `portfolio-bot`).
4. Create and download a JSON key for that service account (Keys → Add Key → JSON). Keep this file safe and do not commit it.

B. Google Sheet (database)
1. Create a new Google Sheet and name it exactly `PortfolioDB`.
2. Create these three tabs (sheet names):
   - `transactions`
   - `mapping`
   - `prices`
3. Share the sheet with the service account `client_email` from the JSON key and grant Editor permissions.

---

## 2. Local installation and run

Open a terminal and work in your project folder (example path below):

```bash
cd c:\Users\alexf\OneDrive\Desktop\AppAndrea\Portfolio-Andrea
```

A. Create & activate a virtual environment

Windows:
```bash
python -m venv venv
.\venv\Scripts\activate
```

macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

B. Requirements

Ensure `requirements.txt` contains:
```
streamlit
pandas
yfinance
plotly
gspread
google-auth
```

Install:
```bash
pip install -r requirements.txt
```

C. Local secrets (Streamlit)

Create a folder `.streamlit` in the project root and a file `secrets.toml` with the `[gcp_service_account]` table. Copy values exactly from the JSON key.

Example `.streamlit/secrets.toml`:
```toml
[gcp_service_account]
type = "service_account"
project_id = "YOUR_PROJECT_ID"
private_key_id = "YOUR_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "portfolio-bot@YOUR_PROJECT_ID.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

D. Run the app locally:
```bash
streamlit run app.py
```

---

## 3. Deployment — GitHub + Streamlit Cloud

1. Initialize a Git repo and push your project to GitHub. Do NOT include `.streamlit/secrets.toml` or your JSON key.
2. On Streamlit Cloud (https://streamlit.io/cloud) create a new app and connect the GitHub repository.
3. In the app settings on Streamlit Cloud, add the same `gcp_service_account` table under "Secrets" (paste TOML fields).
4. Deploy. Streamlit Cloud exposes the secrets as `st.secrets["gcp_service_account"]`.

---

## 4. Troubleshooting & tips

- st.set_page_config must be called only once (preferably in `app.py`). Remove duplicates from files inside `pages/`.
- KeyError on `st.page_link`: some deploy environments do not expose page metadata. Use a safe fallback:
  - Wrap `st.page_link(...)` in try/except and render a markdown link fallback if it fails.
- If Google Sheets access fails:
  - Verify the service account email has Editor access to the sheet.
  - Verify sheet name `PortfolioDB` and tab names (`transactions`, `mapping`, `prices`) match exactly.
  - Verify `secrets.toml` values are correct.
- If you face Streamlit API issues, update Streamlit:
```bash
pip install --upgrade streamlit
```

---

## 5. Security notes

- Never commit the JSON key or `.streamlit/secrets.toml` to source control.
- Add these lines to `.gitignore`:
```
/.streamlit/secrets.toml
credentials.json
```

---

# TO DO
-controllare il fatto che deve aggiungere sogli gli etf che possiedo e non tutti quelli presenti, e di quelli che posside appunto solo gli ultimi di cui mancano le date 
# 📈 Portfolio Cloud Manager

A self-hosted, professional portfolio tracker built with **Python** and **Streamlit**.
It uses a free **Neon (PostgreSQL)** database for fast, reliable data storage and **Yahoo Finance** for pricing data.

### Key Features
- ☁️ Cloud persistence on a robust PostgreSQL database (Neon).
- 💰 Tracks invested capital vs. market value, including fees.
- 📊 Interactive charts (pie, historical, treemap, and performance analysis).
- 🚀 CSV importer for DEGIRO (`Transactions.csv`).
- 💸 Personal budget management (income/expenses).
- ⚖️ Performance comparison against a benchmark of your choice (e.g., SWDA.MI).

---

## 1. Prerequisites — Neon Database

Before running the app, you must set up a free PostgreSQL database on Neon.

1.  Go to [Neon.tech](https://neon.tech) and sign up (the "Free" plan is sufficient).
2.  Create a new project (e.g., `portfolio-app`).
3.  Once the database is ready, find the **Connection Details** on your project dashboard.
4.  Select the **Connection string** or **URI** option. It will show a string like this:
    `postgres://<user>:<password>@<host>/<dbname>`
5.  Keep this string handy for the configuration step.

---

## 2. Local Installation & Setup

Open a terminal and navigate to the project folder.

```bash
cd c:\Users\alexf\OneDrive\Desktop\AppAndrea\Portfolio-Andrea
```

### A. Create and activate a virtual environment

For Windows:
```bash
python -m venv venv
.\venv\Scripts\activate
```

For macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### B. Install requirements

Ensure your `requirements.txt` file contains the following:
```
streamlit
pandas
yfinance
plotly
psycopg2-binary
sqlalchemy
```

Then, install the libraries:
```bash
pip install -r requirements.txt
```

### C. Configure local secrets

1.  Create a folder named `.streamlit` in the project's root directory (if it doesn't already exist).
2.  Inside that folder, create a file named `secrets.toml`.
3.  Paste the template below into the file and fill it out using the **Connection string** you got from Neon.

**Example `secrets.toml`:**
```toml
# .streamlit/secrets.toml
[connections.postgresql]
dialect = "postgresql"
host = "ep-xxxxxxxx-xxxx.eu-central-1.aws.neon.tech" # <-- PASTE YOUR HOST FROM NEON
port = "5432"
database = "neondb" # <-- PASTE YOUR DB NAME FROM NEON
username = "your_username" # <-- PASTE YOUR USERNAME FROM NEON
password = "your_password" # <-- PASTE YOUR PASSWORD FROM NEON
```

### D. Run the application
```bash
streamlit run app.py
```

---

## 3. Deployment — GitHub + Streamlit Cloud

1.  Initialize a Git repository and push your project to a new repository on GitHub.
2.  On [Streamlit Cloud](https://streamlit.io/cloud), create a new app and connect it to your GitHub repository.
3.  In the app's advanced settings (`Settings > Secrets`), paste the same content from your local `secrets.toml` file.
4.  Deploy the app. Streamlit Cloud will securely provide the secrets to your running application.

---

## 4. Security Note

- **Never** commit your `.streamlit/secrets.toml` file to Git.
- Ensure your `.gitignore` file contains the following line to prevent accidental uploads:
```
/.streamlit/secrets.toml
```

---

# TO DO
-controllare il fatto che deve aggiungere sogli gli etf che possiedo e non tutti quelli presenti, e di quelli che posside appunto solo gli ultimi di cui mancano le date 
# Banklytics

Banklytics is a synthetic-data banking transaction analysis system for academic demonstration. It uses synthetic data only and is not a real banking service. Never enter real banking credentials or customer financial information.

## Features

- Customer and simulated account management
- Deposit and withdrawal entry with positive-amount and balance validation
- Account balances, transaction history, CSV export, monthly reports, and unusual-transaction flags
- Registration, login, logout, password hashing, and restricted administrator analytics
- Pandas/NumPy monthly analysis, Chart.js dashboard chart, and Matplotlib chart endpoint
- Downloadable PDF transaction receipts and account statements marked as an educational simulation

## Technology

- Python, Flask, SQLAlchemy
- SQLite for local development or MySQL through PyMySQL
- Pandas, NumPy, Matplotlib, Chart.js, and ReportLab
- Bootstrap 5

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The app seeds demonstration data on first run.

Register the first local user at `/register`. New users are standard customer-role users; administrator access is deliberately not assigned automatically. An authorized operator may set a user's `role` to `admin` directly in the protected database for demonstration purposes.

## Analytics and documents

The dashboard and reports aggregate stored transactions through Pandas and NumPy. A Matplotlib chart is available at `/reports/monthly-chart.png`, while interactive dashboard charts use Chart.js. Each transaction supports a downloadable PDF receipt; each account supports a monthly or all-activity PDF statement. Every PDF prominently identifies itself as an educational simulation.

## MySQL

Create a database named `banklytics`, then copy `.env.example` to `.env` and set:

```env
DATABASE_URL=mysql+pymysql://USER:PASSWORD@localhost:3306/banklytics
```

Flask-SQLAlchemy creates the required tables at startup. All data is synthetic; do not enter banking credentials or real customer information.

## Deploy on Render

This project is ready for a Render Python web service. `render.yaml` supplies the build and start commands; it deliberately does not provision a paid database service.

1. Create a hosted MySQL 8 database with TLS enabled (for example, through a managed database provider).
2. Create the target database and a least-privilege application user with access only to that database.
3. In Render, create a Web Service from this repository and either accept `render.yaml` or use the commands below.
4. Set the required environment variables in the Render dashboard. Do not place secrets in `render.yaml`, the repository, or a local `.env` file that is committed.
5. Deploy. The app performs additive table initialization only; it never drops or truncates tables. Production does not seed sample records unless `AUTO_SEED_DEMO_DATA=true` is explicitly set.

Required Render environment variables:

```text
FLASK_ENV=production
SECRET_KEY=<long random value>
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/banklytics?charset=utf8mb4
SESSION_COOKIE_SECURE=true
AUTO_SEED_DEMO_DATA=false
```

Optional variables: `UNUSUAL_TRANSACTION_LIMIT`, `SESSION_LIFETIME_SECONDS`, and `RATELIMIT_STORAGE_URI`. Use a shared Redis-compatible rate-limit store for multiple Render instances; the default in-memory limiter is suitable only for one instance.

Render build command:

```text
pip install -r requirements.txt
```

Render start command:

```text
gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app
```

Render health check path: `/health`.

For hosted MySQL, URL-encode special characters in the password. If the provider requires TLS, append its documented SSL query options to `DATABASE_URL`; do not disable certificate verification.

## Main routes

| Route | Purpose |
| --- | --- |
| `/register`, `/login`, `/logout` | User authentication |
| `/` | Dashboard |
| `/customers`, `/accounts` | Demo customer and account records |
| `/transactions` | Record, filter, and review transactions |
| `/reports` | Account and monthly summaries |
| `/reports/monthly-chart.png` | Matplotlib monthly cash-flow chart |
| `/export/transactions.csv` | Transaction export |
| `/admin` | Restricted administrator dashboard |

## Project structure

```text
app.py              Flask routes, models, validation, analytics, and PDF generation
config.py           Environment-based application configuration
templates/          Jinja user interface templates
static/css/         Application styling
tests/              Isolated automated tests
```

## Test

```powershell
pytest -q
```

## Security and data policy

Password values are stored only as hashes. Local `.env` files, databases, virtual environments, test caches, and common private-key formats are excluded from version control. The included `.env.example` contains placeholders only.

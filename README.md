# AccountPulse

**Project 16 — Banking Transaction Analysis System · Intermediate**

AccountPulse is a locally runnable Flask application for recording simulated banking transactions and explaining them through dashboards, monthly statements, and rule-based review prompts. It is designed for an academic Python demonstration.

**Educational simulation only.** All balances are simulated and all financial data must be synthetic. AccountPulse is not a bank, does not move real money, and must never store real banking credentials or sensitive customer financial information.

## Features

- Responsive landing page and navy/teal dashboard with original AccountPulse branding.
- Registration, hashed passwords, login sessions, POST logout, and protected account pages.
- A unique demo account number for each new customer, starting at ₹0.
- Deposits and withdrawals with exact Decimal arithmetic, positive-amount validation, and insufficient-balance rejection.
- Atomic balance/ledger updates, MySQL row locking, and idempotent transaction submissions.
- Searchable, date-filtered, type-filtered, sortable, paginated transaction history and CSV export.
- Database-driven financial statistics and interactive Chart.js visualizations.
- Monthly opening/closing balances, deposit/withdrawal totals, counts, CSV statements, and professional PDF statements.
- Downloadable analytical charts generated with Matplotlib.
- Explainable educational transaction review flags and a mark-reviewed action.
- Profile name/email updates and read-only account identity details.
- Explicit, repeatable creation of five zero-balance demo accounts without invented transactions.

## Technology

| Area | Technology |
| --- | --- |
| Runtime | Python 3.13 |
| Web application | Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF |
| Database | MySQL 8.0 / InnoDB, SQLAlchemy ORM, PyMySQL |
| Security | Werkzeug password hashing, CSRF protection, Flask-Limiter |
| Analysis | Pandas, NumPy, Python Decimal |
| Charts | Chart.js in the browser; Matplotlib for PNG exports |
| Interface | HTML5, CSS3, Bootstrap 5, Bootstrap Icons, JavaScript |
| Statements | CSV and ReportLab PDF |
| Configuration/testing | python-dotenv, pytest, Flask test client |

The application uses MySQL. It never silently switches to SQLite. SQLite is used only by isolated automated tests; MySQL-specific locking has a separate integration suite.

## Reviewing the prepared local workspace

The delivered workspace has a dedicated MySQL 8.0 Docker container named `accountpulse-local-mysql`, with its data retained in the `accountpulse-mysql-data` Docker volume. It publishes MySQL only on `127.0.0.1:3306`. Local configuration is in the ignored `.env` file. Private generated demo login instructions are in `.local/demo-access.txt`; open that file locally and do not publish it.

For this prepared workspace, activate `.venv`, ensure the Docker container is running, and run `python run.py`. The manual installation steps below are for a fresh local installation.

## Project structure

```text
accountpulse/
├── app/
│   ├── __init__.py          # Application factory, extensions, error handling
│   ├── cli.py               # Safe inspection, initialization, demo seeding
│   ├── config.py
│   ├── extensions.py
│   ├── forms.py
│   ├── models.py
│   ├── routes/              # Authentication, banking, analytics, reports, profile
│   ├── services/            # Banking, flags, analysis, exports
│   ├── static/              # CSS, JavaScript, logo and local frontend assets
│   └── templates/           # Complete pages and shared layout
├── tests/                   # Isolated unit/route tests and opt-in MySQL tests
├── scripts/
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── README.md
└── PROJECT_EXPLANATION.md
```

## Installation

### 1. Create a Python 3.13 environment

Open a terminal in the project directory:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows, use `py -3.13 -m venv .venv`, then `.venv\Scripts\activate` instead of the activation command above. Once activated, `python --version` should report Python 3.13.

### 2. Inspect MySQL before changing anything

For a new installation with Docker and no existing `.env`, the optional helper can provision a dedicated local server and generate private local database configuration:

```bash
python scripts/local_mysql.py
```

It uses the local Docker socket, creates a named persistent data volume, and exposes MySQL on the loopback interface. It reuses its own existing container without resetting data and refuses to replace an existing `.env` or credential file. After MySQL finishes starting, continue with the inspection and initialization commands in step 4; the helper has already generated `.env`. It does not initialize tables or seed accounts. Keep `.local/mysql.env` private. If you already have MySQL or prefer manual configuration, follow the steps below instead.

Start your existing MySQL 8.0 service and connect using your local administrator account:

```bash
mysql -u root -p
```

Inspect whether the requested database already exists:

```sql
SHOW DATABASES LIKE 'banking_analysis';
```

If it exists, inspect its tables and preserve its records. Do not drop, truncate, reset, or replace an existing database. If it does not exist, create it:

```sql
CREATE DATABASE IF NOT EXISTS banking_analysis
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

Create a dedicated application user if one does not already exist. Replace `CHOOSE_A_LOCAL_DATABASE_PASSWORD` with a password chosen locally; this is a placeholder, not a working credential:

```sql
CREATE USER IF NOT EXISTS 'accountpulse'@'localhost'
  IDENTIFIED BY 'CHOOSE_A_LOCAL_DATABASE_PASSWORD';
GRANT SELECT, INSERT, UPDATE, CREATE, REFERENCES, INDEX
  ON banking_analysis.* TO 'accountpulse'@'localhost';
```

The account needs `CREATE`, `REFERENCES`, and `INDEX` during initial table creation. A database administrator can reduce its ongoing privileges to `SELECT, INSERT, UPDATE` after initialization. No application feature requires `DROP` or `TRUNCATE` privileges. If connecting from another machine or container, use a host-specific MySQL account matching that connection and the appropriate local networking configuration.

### 3. Configure local environment variables

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Put the generated value in `SECRET_KEY` in `.env`. Configure the database URL with the user/password created above:

```dotenv
SECRET_KEY=YOUR_GENERATED_RANDOM_KEY
DATABASE_URL=mysql+pymysql://accountpulse:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:3306/banking_analysis?charset=utf8mb4
COOKIE_SECURE=false
FLAG_LARGE_THRESHOLD=100000.00
RATELIMIT_STORAGE_URI=memory://
```

URL-encode reserved characters such as `@`, `:`, `/`, `#`, and `%` in the database password when placing it in a URL. `.env` is ignored by version control. Never commit it, database credentials, demo passwords, or generated local secret files.

`COOKIE_SECURE=false` allows local HTTP cookies. Use `true` if the application is later served over HTTPS. The current task configures local execution only.

### 4. Inspect and initialize safely

```bash
flask --app run.py inspect-db
flask --app run.py init-db
flask --app run.py inspect-db
```

`inspect-db` prints table/column names and row counts without printing customer records. `init-db` creates only missing tables. It refuses existing AccountPulse tables that lack required columns or do not use the transactional InnoDB engine, so an incompatible existing schema requires an explicit, reviewed data-preserving migration. It does not alter, delete, or reseed existing data automatically.

### 5. Create the five initial demo accounts

```bash
flask --app run.py seed-demo
```

The command securely prompts for a development-only password and confirmation. Choose at least 10 characters including a letter and a digit. The chosen password is applied only to newly created demo accounts. It is hashed before storage and is never displayed on the website.

| Account number | Customer | Login username |
| --- | --- | --- |
| 1001 | Demo Customer 1 | demo1 |
| 1002 | Demo Customer 2 | demo2 |
| 1003 | Demo Customer 3 | demo3 |
| 1004 | Demo Customer 4 | demo4 |
| 1005 | Demo Customer 5 | demo5 |

Each account starts at ₹0 and has no transactions. Sign in with a listed username and the password you entered. An optional local `DEMO_PASSWORD` environment variable can supply the password for scripted development setup; do not commit its value or pass it through a public command log.

Re-running the seeder creates missing demo accounts only. It never resets existing balances, passwords, or transaction histories. If a reserved account number or demo identity conflicts with existing data, it stops without overwriting that data. New users can register additional accounts through the website.

### 6. Start AccountPulse

```bash
python run.py
```

Open **http://127.0.0.1:5000**. The server binds to the local loopback address and runs without debug mode. It checks the database connection before starting. Missing database configuration or a failed connection produces an actionable error rather than a fallback database.

For subsequent sessions, activate `.venv`, ensure MySQL is running, and run the same command. No reseeding is necessary; MySQL retains the data.

## Suggested demonstration

1. Open the landing page and explain the simulation notice.
2. Register a synthetic customer or sign in as `demo1`.
3. Show the empty dashboard and ₹0 initial balance.
4. Deposit ₹1,500.50 and withdraw ₹250.25; the balance becomes ₹1,250.25.
5. Try withdrawing more than the available balance and show its rejection.
6. Filter the transaction history and download CSV.
7. Open Analytics and interact with its charts, then download a PNG.
8. Select the current month in Reports and download its CSV/PDF statement.
9. Explain that review flags are rules for discussion, not accusations or machine learning.
10. Update a synthetic profile name/email and sign out.

Any transactions entered during the demonstration are retained; the application does not generate or erase them automatically.

## Analytics and financial calculations

Financial amounts use `DECIMAL(15,2)` in MySQL and `Decimal` in banking logic. Inputs accept positive amounts with at most two decimal places. Scientific notation, commas, zero, negative values, and non-numeric inputs are rejected.

For analysis, Pandas receives an account-scoped transaction table with amount values converted to integer paise. Python integers retain exact sums. Pandas groups by account, transaction type, and calendar month. NumPy computes transaction counts and aggregate inputs; averages are finalized with Decimal and rounded to two decimal places. Only the coordinates sent to Chart.js/Matplotlib become floating-point values for visualization.

- **Total deposits / withdrawals:** sum of each transaction type.
- **Net change:** deposits minus withdrawals.
- **Average transaction value:** sum of all transaction amounts divided by transaction count; ₹0 for an empty history.
- **Monthly volume:** deposits plus withdrawals during that UTC month.
- **Frequency:** number of transactions per month.
- **Opening balance:** the ledger balance immediately before the selected month.
- **Closing balance:** opening balance plus monthly deposits minus monthly withdrawals.
- **Empty month:** zero volume/count, with opening balance carried forward as closing balance.

For compatible imported data with a pre-existing opening balance, the services infer the baseline from the first ledger entry instead of inventing a deposit. All dashboard queries, exports, and charts are restricted to the signed-in account.

Chart.js displays deposit-versus-withdrawal comparisons, transaction type distribution, monthly activity, and net cash flow. Matplotlib produces a standalone PNG containing monthly deposits/withdrawals and closing-balance trends. The PDF statement includes identity, monthly totals, transaction details, UTC labels, pagination, and the simulation notice.

## Database schema

| Table | Purpose and key fields |
| --- | --- |
| `customers` | `customer_id` primary key; unique username/email; full name; password hash; UTC creation time |
| `accounts` | `account_id` primary key; unique account number; unique customer foreign key; account type; Decimal balance; creation time |
| `transactions` | `transaction_id` primary key; account foreign key; UTC date; constrained type; amount; description; balance after; unique submission key |
| `transaction_flags` | `flag_id` primary key; transaction foreign key; rule name/reason; pending/reviewed status; creation time |

A customer has one account. An account has many transactions. A transaction can have several different review flags. Foreign keys, uniqueness constraints, positive-amount/nonnegative-balance checks, and an account/date transaction index support consistency and efficient history access. Timestamps are stored consistently as naive UTC values and labelled UTC in the interface and exports.

The banking service locks the account row with `SELECT ... FOR UPDATE`, checks the submission key, validates the resulting balance, updates the account, inserts the ledger entry, and creates review flags within one database transaction. Any failure rolls back the whole operation. Repeating the same accepted submission key and payload returns the original transaction; reusing it with changed content is rejected.

## Educational review rules

Flags do not block ordinary valid transactions or declare fraud. They invite manual review:

| Rule | Default trigger |
| --- | --- |
| Large amount | A single amount greater than ₹100,000; configurable with `FLAG_LARGE_THRESHOLD` |
| Frequent withdrawals | At least three withdrawals within ten minutes |
| Above historical average | More than three times the historical average after at least five earlier transactions |

The review page explains each trigger and lets the account owner mark a flag reviewed. The system uses deterministic rules, not machine learning.

## Tests

Run isolated route/service tests from the project directory:

```bash
python -m pytest -q tests
```

These tests create their own SQLite databases with testing configuration. They never run destructive operations against `banking_analysis`. MySQL tests are skipped unless `TEST_MYSQL_URL` is explicitly configured.

For actual MySQL locking and concurrency tests, create a **new, empty, dedicated** MySQL database whose name begins with `ap_test_`. Use a separate local test user with the privileges to create and remove tables in that schema. Then run:

```bash
# Set TEST_MYSQL_URL in your local environment to the dedicated test schema URL.
python -m pytest -q tests -m mysql
```

The MySQL fixture refuses a URL naming `banking_analysis`, a name without the `ap_test_` prefix, or any schema that already has tables. It creates and removes only its own tables in the dedicated empty test schema. Never point it at valuable data. It verifies concurrent withdrawals, concurrent duplicate submissions, and Decimal/data persistence across a recreated application instance.

Coverage includes authentication, validation, CSRF/access control, demo seeding/idempotency, ledger accuracy, Decimal precision, insufficient funds, repeated submissions, reports and exports, unusual-transaction rules, account isolation, rollback, and persistence. See the final project delivery notes for the checks actually executed in the build environment.

### Verified build results — 2 November 2026

- The complete automated suite passed: **83 tests passed in 16.09 seconds**, including four real MySQL integration tests.
- Verification used **Python 3.13.5** and **MySQL 8.0.46**.
- `uv pip check` confirmed compatibility of all 48 installed packages.
- The local `banking_analysis` database contains all four application tables using InnoDB. Its initial demo state contains exactly five accounts, each with a ₹0 balance, and no generated transactions.
- MySQL integration checks ran against a separate dedicated test schema. The application database was preserved.
- Browser verification passed for all authenticated pages with HTTP 200 responses. Both dashboard charts and all four analytics charts rendered without JavaScript or network errors. At a 390-pixel viewport, the dashboard had no horizontal overflow, and the sidebar and profile dropdown worked. Real-browser sign-in and valid CSRF form submissions were also verified.

## Screenshots

These captures were taken from the running application using synthetic data:

| View | Screenshot |
| --- | --- |
| Landing page | [landing.png](docs/screenshots/landing.png) |
| Account dashboard | [dashboard.png](docs/screenshots/dashboard.png) |
| Analytics | [analytics.png](docs/screenshots/analytics.png) |
| Mobile dashboard | [mobile-dashboard.png](docs/screenshots/mobile-dashboard.png) |

Screenshots are documentation artifacts rather than application data. They do not seed or modify the five initial demo accounts.

## Troubleshooting

- **Missing SECRET_KEY:** generate a random value and save it in `.env`.
- **Cannot connect to MySQL:** start MySQL; check its host/port, database name, user grants, URL-encoded password, and `DATABASE_URL`.
- **Missing tables:** inspect first, then run `flask --app run.py init-db`.
- **Existing schema mismatch:** preserve the database and prepare a reviewed additive migration; never reset it to make the error disappear.
- **CSRF/form expired:** reload the page and submit again. Browser cookies must be enabled.
- **Rate limited:** wait for the indicated period. Registration is limited to ten POST attempts/hour and login to ten/minute per client address.
- **Port 5000 in use:** stop the other local process using it before running the default command.
- **Empty charts:** no transactions is a valid state. Record a deposit or withdrawal to create real chart data.

## Security and scope

Passwords use Werkzeug's salted password hashing. Forms use CSRF tokens. SQLAlchemy parameterizes queries. Protected routes derive the account from the authenticated session, and review updates also check ownership. Session cookies are HTTP-only with SameSite=Lax; sensitive pages use `Cache-Control: no-store`. Browser security headers restrict scripts/resources and framing. CSV exports neutralize user-controlled spreadsheet formulas.

Login rate limits use process memory by default, which is appropriate for one local development process. Multiple workers would need shared storage. The Flask development server, educational rules, and current local configuration are intended for a classroom simulation. Do not treat this application as a production banking system.

## Future enhancements

Possible later work includes reviewed schema migrations, optional password changes/recovery, richer budgeting categories, accessibility audits, larger-ledger query optimizations, shared rate-limit storage, and scheduled synthetic statements. Any future real financial integration would require a separate design and security review and is outside this project.

# AccountPulse — Project Explanation

**Project 16: Banking Transaction Analysis System**  
**Difficulty: Intermediate**

## Project aim

AccountPulse demonstrates how Python can record transactions in a relational database and turn them into useful financial summaries. A user creates a demo account, deposits or withdraws simulated money, and studies the resulting history, charts, and monthly statements.

Every balance is simulated. The application does not connect to a real bank, process payments, or transfer money. Only synthetic names and financial records should be used.

## Problem statement

A list of deposits and withdrawals is difficult to understand on its own. A user needs to know how much was deposited, how much was withdrawn, the balance after each action, how activity changes by month, and which unusual patterns deserve a closer look.

This project stores the original transactions reliably, calculates summaries from those stored records, and presents them in a clear web interface. It also shows basic authentication, authorization, data validation, and database transaction safety.

## What the user can do

The user can register, sign in, see an account dashboard, record deposits and withdrawals, search and filter transaction history, download CSV data, explore analytics, select monthly statements, download PDF reports, review rule-based flags, update a profile, and sign out.

The five initial demo accounts are numbered 1001–1005 and belong to Demo Customer 1–5. Their usernames are `demo1`–`demo5`. They start at ₹0 with no invented transactions. A local setup command asks the presenter to choose the demo password; the website does not reveal it.

## Why Flask is used

Flask is a lightweight Python web framework. It receives a browser request, runs the relevant Python function, and returns an HTML page or downloadable file. It is suitable for an intermediate project because the request/response flow remains easy to explain.

AccountPulse uses blueprints to separate authentication, banking, history, analytics, reports, and profile pages. Templates contain the page layout; service modules contain business rules. This separation makes the code easier to inspect and maintain.

## Why MySQL is used

MySQL stores records permanently, so stopping Flask does not erase an account or its transaction history. Its relational structure lets the application connect customers to accounts, accounts to transactions, and transactions to review flags.

MySQL InnoDB also supports database transactions and row locks. These are essential when two requests try to withdraw from the same balance at the same time. A request locks the account, validates the latest balance, and saves all related changes together.

The main database is named `banking_analysis`. Setup creates missing tables safely. It does not drop existing records or recreate demo accounts on every server restart.

## Database relationships

| Relationship | Meaning |
| --- | --- |
| Customer → Account | One customer owns one demo account |
| Account → Transactions | One account can contain many deposits and withdrawals |
| Transaction → Flags | One transaction can trigger several different review rules |

The `customers` table stores identity and a password hash. The `accounts` table stores the account number and current balance. The `transactions` table stores the amount, type, date, description, and balance after the action. The `transaction_flags` table stores the rule name, explanation, and review status.

Primary keys identify records. Foreign keys connect related records. Unique constraints prevent duplicate usernames, account numbers, and submission keys. Check constraints restrict transaction types, reject nonpositive amounts, and prevent negative balances.

## Why Decimal is used for money

Binary floating-point numbers cannot represent every decimal fraction exactly. For example, ordinary float calculations involving 0.1 and 0.2 can contain a small rounding difference.

AccountPulse uses Python `Decimal` in the banking service and MySQL `DECIMAL(15,2)` for stored amounts. It accepts at most two decimal places. Therefore, a ₹0.10 deposit followed by ₹0.20 produces exactly ₹0.30.

For analysis, amounts become integer paise. ₹123.45 becomes 12,345 paise, so grouping and summing still use exact arithmetic. Floating-point numbers are used only for drawing chart coordinates.

## Deposit flow

1. The authenticated user opens the deposit form.
2. The page supplies a CSRF token and a unique submission token.
3. The server validates that the amount is positive and has no more than two decimal places.
4. The banking service locks the account row and checks whether this submission was already processed.
5. It adds the amount to the current balance and creates a deposit ledger entry with the resulting balance.
6. It evaluates review rules and saves any matching flags.
7. One database commit saves the balance, transaction, and flags together.
8. The next dashboard/history request reads the updated database values.

## Withdrawal flow

Withdrawal follows the same flow, with an additional balance check. If the requested amount exceeds the available simulated balance, the service rejects it and rolls back. Otherwise, it subtracts the amount and saves the withdrawal and resulting balance atomically.

If any part of the database operation fails, the whole operation rolls back. The account cannot be changed without its matching ledger entry.

## Concurrent requests and repeated submissions

Two requests must not both rely on an outdated balance. `SELECT ... FOR UPDATE` makes one request wait while another operates on the same account. The waiting request then validates the latest committed balance.

A unique submission key also prevents an accidental double click or retried accepted form from adding the same transaction twice. The same key with the same content returns the existing record. Reusing it with different content is rejected.

SQLite is useful for isolated route tests, but it does not demonstrate the same locking behavior as MySQL. The project therefore includes separate MySQL concurrency tests against a dedicated empty test database.

## How Pandas works in this project

Pandas provides a DataFrame, which is like a table inside Python. AccountPulse builds it from the signed-in account's transactions, including date, type, amount in paise, and resulting balance.

The analysis service uses grouping to answer questions such as:

- How much was deposited and withdrawn?
- What happened in each calendar month?
- How many transactions happened per month?
- What was the closing balance in each month?

The DataFrame is built from real stored simulated transactions. The charts do not contain fabricated dashboard statistics.

## How NumPy works in this project

NumPy works efficiently with arrays. AccountPulse uses transaction-type arrays to count deposits and withdrawals and uses amount arrays as inputs to aggregate statistics. Exact integer values are retained when summing financial inputs. Decimal is used to finalize the rounded average amount.

NumPy also provides chart positions for Matplotlib. It supports the analysis process rather than replacing the database.

## How Matplotlib works in this project

Matplotlib creates a downloadable PNG chart on the server. The image compares monthly deposits and withdrawals and shows the account's closing-balance trend. It is useful for including results in an academic report or presentation.

The website uses Chart.js for interactive browser charts. Matplotlib is used for a portable image that can be downloaded and shared. Both read the same calculated account statistics.

## Analytics calculations

| Measure | Calculation |
| --- | --- |
| Total deposits | Sum of deposit amounts |
| Total withdrawals | Sum of withdrawal amounts |
| Net change | Deposits − withdrawals |
| Transaction count | Number of stored transactions |
| Average amount | Sum of all amounts ÷ transaction count |
| Highest deposit/withdrawal | Maximum amount of the selected type |
| Monthly volume | Monthly deposits + monthly withdrawals |
| Monthly net flow | Monthly deposits − monthly withdrawals |
| Closing balance | Opening balance + deposits − withdrawals |

When there are no transactions, counts and flow totals are zero. The average is also shown as zero rather than attempting division by zero. A month without transactions carries its opening balance forward as its closing balance.

Dates are stored in UTC and monthly boundaries use UTC. This avoids mixing local time zones during filtering and reporting.

## Example calculation

A new account has an opening balance of ₹0.00. It receives a ₹1,500.50 deposit and a ₹250.25 withdrawal.

- Total deposits: ₹1,500.50.
- Total withdrawals: ₹250.25.
- Closing balance and net change: ₹1,250.25.
- Transaction count: 2.
- Average transaction amount: (₹1,500.50 + ₹250.25) ÷ 2 = ₹875.38 after rounding.

If no transactions occur in the following month, its opening and closing balances are both ₹1,250.25, while its deposit/withdrawal totals and transaction count are zero.

## Unusual transaction review

The application uses simple, explainable rules:

- A transaction exceeds a configurable large-amount threshold, initially ₹100,000.
- At least three withdrawals occur within ten minutes.
- A transaction is more than three times the historical average after at least five earlier transactions.

A matching transaction receives a review flag with a reason. The user can mark the flag reviewed. This is an educational prompt, not an accusation of fraud. The project does not claim to use machine learning.

## Security controls

Passwords are stored as salted hashes rather than readable text. Flask-Login manages authenticated sessions. CSRF tokens protect state-changing forms. SQLAlchemy builds parameterized queries. The application derives account access from the signed-in user rather than trusting a supplied account number.

Input validation limits amounts and text fields. Login and registration have request rate limits. Logout uses POST. Cookies are HTTP-only with SameSite settings, and configuration can enable HTTPS-only cookies. Secrets belong in the ignored `.env` file. Downloaded CSV data neutralizes user-entered spreadsheet formulas.

These controls demonstrate good engineering practices for an educational system. They do not make it suitable for real banking.

## Testing approach

Pytest and the Flask test client check pages, registration, duplicate users, login/logout, protected routes, deposit/withdrawal validation, precision, reports, flags, ownership checks, rollback, repeated submissions, and persistence.

Most tests use a separate temporary SQLite database. MySQL integration tests use a dedicated empty database beginning with `ap_test_` and check real row-lock behavior, concurrent duplicate submissions, and persistence. The integration fixture refuses the main `banking_analysis` database and any nonempty test schema.

## Possible viva questions and answers

**What is the objective of AccountPulse?**  
To record synthetic banking transactions accurately and explain them through summaries, charts, statements, and review rules.

**Is this a real banking application?**  
No. It is an educational simulation with no real payments, bank integrations, or transfers.

**What is an ORM?**  
An object-relational mapper connects Python classes and objects to database tables and records. This project uses SQLAlchemy.

**Why is an account number unique?**  
It must identify exactly one demo account. A database unique constraint enforces that rule.

**Why is a foreign key useful?**  
It ensures a transaction refers to an existing account and a flag refers to an existing transaction.

**Why is a balance stored alongside a transaction ledger?**  
The balance gives a convenient current value, while the ledger provides history and a balance-after audit trail. Both are updated in the same atomic operation.

**What is a database transaction?**  
A group of changes that succeeds together or rolls back together. Here it includes the account balance, ledger entry, and review flags.

**What prevents an overdraft during simultaneous withdrawals?**  
An InnoDB account row lock serializes the operations, and each request checks the latest balance before committing.

**What prevents a repeated accepted deposit?**  
A unique submission key plus a check of the original transaction payload.

**Why not use float for money?**  
Float can introduce binary rounding differences. Decimal and integer paise preserve exact financial values.

**What is the difference between authentication and authorization?**  
Authentication confirms who signed in. Authorization checks which records that user may access.

**What is CSRF protection?**  
It checks a session-linked form token so another website cannot silently submit a state-changing request as the user.

**Can changing a URL expose another customer's records?**  
Account queries are derived from the signed-in user's account, and flag actions also check ownership.

**What happens when a month has no transactions?**  
Its count and flow totals are zero; the previous balance is carried forward unchanged.

**Why use Pandas and NumPy together?**  
Pandas organizes and groups tabular transaction data. NumPy supports array-based counts, aggregate inputs, and chart coordinates.

**Why use Chart.js and Matplotlib?**  
Chart.js provides interactive website charts. Matplotlib produces standalone downloadable analytical images.

**How is a report different from the dashboard?**  
The dashboard summarizes current account activity; a monthly statement applies explicit month boundaries and includes opening/closing balances and that month's ledger.

**Does an unusual transaction flag prove fraud?**  
No. It only indicates that a documented rule matched and suggests review.

**What happens when the server restarts?**  
MySQL retains the records. The server does not automatically create transactions or duplicate demo accounts.

**How could the project be improved later?**  
With reviewed schema migrations, richer categories, password recovery, larger-ledger optimizations, and shared rate-limit storage, while keeping real financial processing outside this academic scope.

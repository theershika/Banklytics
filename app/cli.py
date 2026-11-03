"""Explicit, additive database setup. Never reset existing records."""
import click
from sqlalchemy import inspect
from .extensions import db
from .models import Customer, Account


def seed_demo_accounts(password):
    if not password or len(password) < 10 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError('Use a development-only password of at least 10 characters including letters and digits.')
    created = 0
    try:
        for i in range(1, 6):
            number = str(1000 + i)
            account = db.session.scalar(db.select(Account).where(Account.account_number == number))
            if account:
                if account.customer.username != f'demo{i}':
                    raise ValueError(f'Account {number} already belongs to an existing customer; no data changed.')
                continue
            username, email = f'demo{i}', f'demo{i}@accountpulse.example'
            if db.session.scalar(db.select(Customer).where((Customer.username == username) | (Customer.email == email))):
                raise ValueError(f'Demo identity {username} already exists without its expected account; inspect it first.')
            customer = Customer(full_name=f'Demo Customer {i}', username=username, email=email)
            customer.set_password(password)
            account = Account(account_number=number, customer=customer, balance=0)
            db.session.add_all([customer, account])
            created += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return created


def validate_existing_schema():
    inspector = inspect(db.engine)
    existing = set(inspector.get_table_names())
    issues = []
    for table in db.metadata.sorted_tables:
        if table.name in existing:
            if db.engine.dialect.name == 'mysql':
                engine = inspector.get_table_options(table.name).get('mysql_engine', '')
                if engine.lower() != 'innodb':
                    issues.append(f'{table.name}: requires the transactional InnoDB engine (found {engine})')
            actual = {c['name'] for c in inspector.get_columns(table.name)}
            missing = set(table.columns.keys()) - actual
            if missing:
                issues.append(f'{table.name}: missing columns {", ".join(sorted(missing))}')
    if issues:
        raise click.ClickException('Existing schema needs a reviewed, data-preserving migration. No tables changed. ' + '; '.join(issues))


def register_cli(app):
    @app.cli.command('inspect-db')
    def inspect_db():
        """Read table names, column names and row counts without personal data."""
        inspector = inspect(db.engine)
        click.echo('Connected database: ' + str(db.engine.url.database))
        for name in inspector.get_table_names():
            table = db.Table(name, db.MetaData(), autoload_with=db.engine)
            count = db.session.scalar(db.select(db.func.count()).select_from(table))
            click.echo(f'{name}: {count} rows; columns: ' + ', '.join(c.name for c in table.columns))

    @app.cli.command('init-db')
    def init_db():
        """Create missing tables only; refuse incompatible existing columns."""
        validate_existing_schema()
        db.create_all()
        click.echo('Missing tables created. Existing tables and records preserved.')

    @app.cli.command('seed-demo')
    @click.option('--password', envvar='DEMO_PASSWORD', prompt=True, hide_input=True, confirmation_prompt=True)
    def seed_demo(password):
        """Seed five zero-balance demo accounts; never reset existing passwords."""
        try:
            count = seed_demo_accounts(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f'Created {count} demo accounts. Existing accounts and balances unchanged.')

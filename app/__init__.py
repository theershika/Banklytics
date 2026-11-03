import os
from decimal import Decimal
from pathlib import Path
from flask import Flask, render_template, request, g
from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from flask_wtf.csrf import CSRFError
from .extensions import db, login_manager, csrf, limiter


def create_app(config=None):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / '.env')
    # Import after dotenv so environment config is resolved correctly.
    from .config import Config
    app = Flask(__name__, instance_path=str(root / 'instance'))
    app.config.from_object(Config)
    # Config can be imported earlier by tooling; prefer current environment.
    if os.getenv('DATABASE_URL'):
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
    if os.getenv('SECRET_KEY'):
        app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    if config:
        app.config.update(config)
    if not app.config.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY is missing. Copy .env.example to .env and generate a random key as described in README.md.')
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if not app.config.get('TESTING') and not uri.startswith('mysql+pymysql://'):
        raise RuntimeError('AccountPulse requires MySQL. Set DATABASE_URL=mysql+pymysql://.../banking_analysis in .env. SQLite is permitted only in isolated tests.')
    os.environ.setdefault('MPLCONFIGDIR', str(root / 'instance' / 'matplotlib'))
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please sign in to access your demo account.'
    from .models import Customer

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(Customer, int(user_id))
        except (ValueError, TypeError):
            return None

    @app.template_filter('money')
    def money(value):
        return f'₹{Decimal(str(value or 0)):,.2f}'

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def render_error(code, title, message):
        return render_template('errors/error.html', code=code, title=title, message=message), code

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_error(400, 'Form expired', 'Your security token is missing or expired. Reload the page and try again.')

    for code, title, message in [(400, 'Invalid request', 'Check your input and try again.'), (404, 'Page not found', 'This page or record is unavailable.'), (429, 'Please slow down', 'Too many attempts. Wait a minute before trying again.'), (500, 'Something went wrong', 'Please retry. If this continues, check the server logs.')]:
        app.register_error_handler(code, lambda error, c=code, t=title, m=message: render_error(c, t, m))

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        # An unavailable database can fail inside the Flask-Login user loader.
        # Render the recovery page without retrying that same database lookup.
        from flask_login import AnonymousUserMixin
        g._login_user = AnonymousUserMixin()
        # Avoid logging credentials or transaction descriptions from SQL parameters.
        app.logger.error('Database operation failed (%s). Verify MySQL availability and schema.', type(error).__name__)
        return render_error(503, 'Database unavailable', 'Start MySQL 8.0, verify DATABASE_URL in .env, then run flask --app run.py init-db. Existing data will be preserved.')

    from .routes import register_blueprints
    register_blueprints(app)
    from .cli import register_cli
    register_cli(app)
    return app

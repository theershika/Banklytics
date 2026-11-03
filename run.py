"""Local development entry point. No automatic schema changes or demo transactions."""
from app import create_app

app = create_app()

if __name__ == '__main__':
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from app.extensions import db
    try:
        with app.app_context():
            db.session.execute(text('SELECT 1'))
    except SQLAlchemyError:
        raise SystemExit('Cannot connect to MySQL. Start MySQL 8.0 and check DATABASE_URL in .env. Then run: flask --app run.py init-db. See README.md.') from None
    app.run(host='127.0.0.1', port=5000, debug=False)

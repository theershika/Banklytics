"""Application blueprint registration."""
def register_blueprints(app):
    from . import auth, dashboard, banking, transactions, analytics, reports, profile
    for bp in (dashboard.main_bp, dashboard.bp, auth.bp, banking.bp, transactions.bp, analytics.bp, reports.bp, profile.bp):
        app.register_blueprint(bp)

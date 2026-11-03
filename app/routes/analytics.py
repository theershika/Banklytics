"""Interactive financial summaries and downloadable analytical images."""
from flask import Blueprint, render_template, send_file
from flask_login import current_user, login_required

bp = Blueprint("analytics", __name__)


@bp.get("/analytics")
@login_required
def index():
    # Pandas and NumPy are only needed for analytics.  Deferring this import
    # keeps the base web service lightweight on small production instances.
    from app.services.analytics_service import get_analytics

    stats = get_analytics(current_user.account.account_id)
    return render_template("analytics.html", stats=stats, chart_data=stats["chart_data"])


@bp.get("/analytics/chart.png")
@login_required
def chart_image():
    from app.services.analytics_service import chart_png

    return send_file(chart_png(current_user.account.account_id), mimetype="image/png", as_attachment=True,
                     download_name="accountpulse-analysis.png")

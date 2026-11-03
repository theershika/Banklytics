"""Accurate monthly balances and portable reports."""
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, Response, send_file, abort
from flask_login import current_user, login_required
from app.services.reporting_service import monthly_report, report_csv, report_pdf

bp = Blueprint("reports", __name__)


def selected_report():
    now = datetime.now(timezone.utc)
    try:
        month = int(request.args.get("month", now.month))
        year = int(request.args.get("year", now.year))
    except (ValueError, TypeError):
        abort(400, description="Choose a valid month and year.")
    if not 1 <= month <= 12 or not 1900 <= year <= 9998:
        abort(400, description="Choose a month from 1–12 and a year from 1900–9998.")
    return monthly_report(current_user.account.account_id, year, month)


@bp.get("/reports")
@login_required
def index():
    report = selected_report()
    return render_template("reports.html", report=report, month=report["month"], year=report["year"])


@bp.get("/reports/monthly.csv")
@login_required
def export_csv():
    report = selected_report()
    filename = f'accountpulse-{report["year"]}-{report["month"]:02d}.csv'
    return Response(report_csv(report), content_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/reports/monthly.pdf")
@login_required
def export_pdf():
    report = selected_report()
    return send_file(report_pdf(report, current_user, current_user.account), mimetype="application/pdf", as_attachment=True,
                     download_name=f'accountpulse-{report["year"]}-{report["month"]:02d}.pdf')

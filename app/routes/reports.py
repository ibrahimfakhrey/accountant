from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, request, g, send_file
from flask_login import login_required
from app.services.reports import balance_sheet, income_statement, cash_flow

bp = Blueprint("reports", __name__)


def _parse_date(s, default=None):
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return default


@bp.route("/")
@login_required
def index():
    return render_template("reports/index.html")


@bp.route("/balance-sheet")
@login_required
def balance():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    as_of = _parse_date(request.args.get("as_of"), date.today())
    data = balance_sheet(g.active_company.id, as_of=as_of)
    return render_template("reports/balance_sheet.html", data=data, as_of=as_of)


@bp.route("/income-statement")
@login_required
def income():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = income_statement(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/income_statement.html", data=data, start=start, end=end)


@bp.route("/cash-flow")
@login_required
def cashflow():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = cash_flow(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/cash_flow.html", data=data, start=start, end=end)


@bp.route("/<report_type>/export/<fmt>")
@login_required
def export(report_type, fmt):
    from app.services.export import export_report
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    file_io, filename, mimetype = export_report(g.active_company, report_type, fmt, start, end)
    return send_file(file_io, as_attachment=True, download_name=filename, mimetype=mimetype)

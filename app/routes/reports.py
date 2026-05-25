from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, request, g, send_file
from flask_login import login_required
from app.services.reports import (
    balance_sheet, income_statement, cash_flow,
    income_summary, expenses_summary, income_statement_compared,
    aging_report, ap_aging_report, vat_report,
    payroll_summary_report, fixed_assets_report,
)

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


@bp.route("/income-summary")
@login_required
def income_summary_view():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = income_summary(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/income_summary.html", data=data, start=start, end=end)


@bp.route("/expenses-summary")
@login_required
def expenses_summary_view():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = expenses_summary(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/expenses_summary.html", data=data, start=start, end=end)


@bp.route("/pl-compared")
@login_required
def pl_compared():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = income_statement_compared(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/pl_compared.html", data=data, start=start, end=end)


@bp.route("/ar-aging")
@login_required
def ar_aging():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    as_of = _parse_date(request.args.get("as_of"), date.today())
    data = aging_report(g.active_company.id, as_of=as_of)
    return render_template("reports/ar_aging.html", data=data, as_of=as_of)


@bp.route("/ap-aging")
@login_required
def ap_aging():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    as_of = _parse_date(request.args.get("as_of"), date.today())
    data = ap_aging_report(g.active_company.id, as_of=as_of)
    return render_template("reports/ap_aging.html", data=data, as_of=as_of)


@bp.route("/vat")
@login_required
def vat():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    data = vat_report(g.active_company.id, start_date=start, end_date=end)
    return render_template("reports/vat.html", data=data, start=start, end=end)


@bp.route("/payroll")
@login_required
def payroll():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    today = date.today()
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    data = payroll_summary_report(g.active_company.id, year=year, month=month)
    return render_template("reports/payroll_summary.html", data=data, year=year, month=month, today=today)


@bp.route("/fixed-assets")
@login_required
def fixed_assets():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    data = fixed_assets_report(g.active_company.id)
    return render_template("reports/fixed_assets.html", data=data)


@bp.route("/<report_type>/export/<fmt>")
@login_required
def export(report_type, fmt):
    from app.services.export import export_report
    today = date.today()
    start = _parse_date(request.args.get("start_date"), today.replace(day=1))
    end = _parse_date(request.args.get("end_date"), today)
    kwargs = {}
    if report_type == "payroll-summary":
        kwargs["year"] = request.args.get("year", type=int)
        kwargs["month"] = request.args.get("month", type=int)
    file_io, filename, mimetype = export_report(g.active_company, report_type, fmt, start, end, **kwargs)
    return send_file(file_io, as_attachment=True, download_name=filename, mimetype=mimetype)

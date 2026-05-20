from flask import Blueprint, render_template, redirect, url_for, g
from flask_login import login_required
from app.services.reports import dashboard_metrics
from app.services.invoicing import update_overdue_statuses

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    update_overdue_statuses(g.active_company.id)
    metrics = dashboard_metrics(g.active_company.id)
    return render_template("dashboard/index.html", metrics=metrics)

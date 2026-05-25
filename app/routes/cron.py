"""Cron tick — call this from an external scheduler (e.g. system cron, GitHub Actions).

POST /cron/tick   — runs all scheduled tasks once
"""
from flask import Blueprint, jsonify, request, current_app
from app.services.reminders import process_invoice_reminders
from app.services.invoicing import update_overdue_statuses
from app.services.journals import process_recurring_journals
from app.models import Company

bp = Blueprint("cron", __name__)


def _authorized():
    token = current_app.config.get("CRON_TOKEN") or ""
    if not token:
        return True   # no token configured → allow (dev)
    provided = request.headers.get("X-Cron-Token") or request.args.get("token", "")
    return provided == token


@bp.route("/tick", methods=["POST", "GET"])
def tick():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    summary = {}

    # Mark overdue invoices across all companies
    overdue_total = 0
    for c in Company.query.filter_by(is_active=True).all():
        overdue_total += update_overdue_statuses(c.id)
    summary["marked_overdue"] = overdue_total

    # Send reminder emails
    summary["reminders"] = process_invoice_reminders()

    # Post any due recurring journal entries
    summary["recurring"] = process_recurring_journals()

    return jsonify(summary)

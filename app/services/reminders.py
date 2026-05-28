"""Invoice reminder processor — runs from the cron tick endpoint.

For each invoice, fire reminders according to its company's `reminder_config`:
  days_before: [int]   — N days before due_date (e.g., [7, 3])
  overdue_days: [int]  — N days after due_date  (e.g., [0, 7, 14])

Each (kind, days) pair fires at most once per invoice via InvoiceReminderSent.
"""
from datetime import date, datetime
from app import db
from app.models import Invoice, InvoiceStatus, InvoiceReminderSent, Company
from app.services.email import send_overdue_reminder
import logging

logger = logging.getLogger("ledgeros.reminders")


def _already_sent(invoice_id, kind, days):
    return InvoiceReminderSent.query.filter_by(
        invoice_id=invoice_id, threshold_kind=kind, threshold_days=days
    ).first() is not None


def _mark_sent(invoice_id, kind, days):
    db.session.add(InvoiceReminderSent(
        invoice_id=invoice_id, threshold_kind=kind, threshold_days=days,
        sent_at=datetime.utcnow(),
    ))


def process_invoice_reminders():
    """Single pass — call from a cron tick. Returns a summary dict."""
    today = date.today()
    sent_counts = {"before": 0, "overdue": 0, "skipped": 0}

    # Cache reminder configs per company to avoid N+1
    company_cfg = {}
    candidates = Invoice.query.filter(
        Invoice.send_reminders.is_(True),
        Invoice.status.in_([
            InvoiceStatus.SENT,
            InvoiceStatus.PARTIALLY_PAID,
            InvoiceStatus.OVERDUE,
        ]),
    ).all()

    for inv in candidates:
        if inv.balance <= 0.01:
            sent_counts["skipped"] += 1
            continue

        cfg = company_cfg.get(inv.company_id)
        if cfg is None:
            company = db.session.get(Company, inv.company_id)
            cfg = company.reminders if company else {}
            company_cfg[inv.company_id] = cfg

        if not cfg.get("enabled", True):
            sent_counts["skipped"] += 1
            continue

        days_until = (inv.due_date - today).days
        # before-due-date thresholds
        for d in cfg.get("days_before", []):
            if days_until == d and not _already_sent(inv.id, "before", d):
                if send_overdue_reminder(inv, f"before_{d}"):
                    _mark_sent(inv.id, "before", d)
                    sent_counts["before"] += 1
        # overdue thresholds (days past due)
        days_overdue = -days_until  # positive = past due
        for d in cfg.get("overdue_days", []):
            if days_overdue == d and days_overdue >= 0 and not _already_sent(inv.id, "overdue", d):
                if send_overdue_reminder(inv, "overdue" if d == 0 else f"overdue_{d}"):
                    _mark_sent(inv.id, "overdue", d)
                    if inv.status != InvoiceStatus.OVERDUE and days_overdue > 0:
                        inv.status = InvoiceStatus.OVERDUE
                    sent_counts["overdue"] += 1

    db.session.commit()
    logger.info("Reminders processed: %s", sent_counts)
    return sent_counts

"""Invoice reminder processor — runs from the cron tick endpoint.

For each company, look for invoices crossing the 7d / 3d / overdue thresholds
that have not yet been notified for that threshold.
"""
from datetime import date, datetime, timedelta
from app import db
from app.models import Invoice, InvoiceStatus
from app.services.email import send_overdue_reminder
import logging

logger = logging.getLogger("ledgeros.reminders")


def process_invoice_reminders():
    """Single pass — call from a cron tick. Returns a summary dict."""
    today = date.today()
    sent_counts = {"before_7": 0, "before_3": 0, "overdue": 0, "skipped": 0}

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
        days_until = (inv.due_date - today).days
        if days_until == 7 and not inv.reminder_7d_sent_at:
            if send_overdue_reminder(inv, "before_7"):
                inv.reminder_7d_sent_at = datetime.utcnow()
                sent_counts["before_7"] += 1
        elif days_until == 3 and not inv.reminder_3d_sent_at:
            if send_overdue_reminder(inv, "before_3"):
                inv.reminder_3d_sent_at = datetime.utcnow()
                sent_counts["before_3"] += 1
        elif days_until < 0 and not inv.overdue_notified_at:
            if send_overdue_reminder(inv, "overdue"):
                inv.overdue_notified_at = datetime.utcnow()
                if inv.status != InvoiceStatus.OVERDUE:
                    inv.status = InvoiceStatus.OVERDUE
                sent_counts["overdue"] += 1

    db.session.commit()
    logger.info("Reminders processed: %s", sent_counts)
    return sent_counts

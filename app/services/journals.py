"""Journal management beyond posting: pause, reactivate, templates, recurring."""
from datetime import datetime, date, timedelta
from app import db
from app.models import JournalEntry, JournalLine, JournalAudit, JournalAction
from app.services.ledger import LedgerError, post_journal


def pause_entry(entry, reason, user_id):
    if not entry.is_active:
        raise LedgerError("القيد موقوف بالفعل")
    if entry.is_reversal:
        raise LedgerError("لا يمكن إيقاف قيد عكسي")
    if not (reason or "").strip():
        raise LedgerError("سبب الإيقاف مطلوب")

    entry.is_active = False
    entry.pause_reason = reason.strip()
    entry.paused_by_id = user_id
    entry.paused_at = datetime.utcnow()
    db.session.add(JournalAudit(
        entry_id=entry.id, user_id=user_id,
        action=JournalAction.PAUSED, reason=reason.strip(),
    ))
    db.session.commit()
    return entry


def reactivate_entry(entry, reason, user_id):
    if entry.is_active:
        raise LedgerError("القيد نشط بالفعل")
    if not (reason or "").strip():
        raise LedgerError("سبب إعادة التنشيط مطلوب")

    entry.is_active = True
    entry.reactivate_reason = reason.strip()
    entry.reactivated_by_id = user_id
    entry.reactivated_at = datetime.utcnow()
    db.session.add(JournalAudit(
        entry_id=entry.id, user_id=user_id,
        action=JournalAction.REACTIVATED, reason=reason.strip(),
    ))
    db.session.commit()
    return entry


def post_from_template(company_id, template, entry_date=None, description=None, created_by=None):
    """Create a balanced journal from a saved template."""
    lines = [
        {"account_id": tl.account_id, "debit": float(tl.debit), "credit": float(tl.credit), "memo": tl.memo}
        for tl in template.lines
    ]
    return post_journal(
        company_id=company_id,
        description=description or f"من قالب: {template.name}",
        lines=lines,
        entry_date=entry_date,
        created_by=created_by,
        source_type="template",
        source_id=template.id,
    )


def _advance_date(current, frequency):
    from app.models import RecurrenceFrequency
    if frequency == RecurrenceFrequency.DAILY:
        return current + timedelta(days=1)
    if frequency == RecurrenceFrequency.WEEKLY:
        return current + timedelta(weeks=1)
    if frequency == RecurrenceFrequency.MONTHLY:
        # Naive month math: same day next month, snap to 28 if needed
        m = current.month + 1
        y = current.year + (1 if m > 12 else 0)
        m = ((m - 1) % 12) + 1
        d = min(current.day, 28)
        return date(y, m, d)
    if frequency == RecurrenceFrequency.YEARLY:
        return date(current.year + 1, current.month, current.day)
    return current


def process_recurring_journals():
    """Run every due recurring schedule. Called from /cron/tick."""
    from app.models import RecurringJournal
    today = date.today()
    due = RecurringJournal.query.filter(
        RecurringJournal.is_active.is_(True),
        RecurringJournal.next_run_date <= today,
    ).all()
    posted = 0
    for sched in due:
        if sched.end_date and sched.next_run_date > sched.end_date:
            sched.is_active = False
            continue
        try:
            post_from_template(
                sched.company_id, sched.template,
                entry_date=sched.next_run_date,
                description=f"{sched.name} ({sched.next_run_date.isoformat()})",
            )
            sched.next_run_date = _advance_date(sched.next_run_date, sched.frequency)
            if sched.end_date and sched.next_run_date > sched.end_date:
                sched.is_active = False
            posted += 1
        except Exception:
            import logging
            logging.getLogger("ledgeros.recurring").exception(
                "Failed to post recurring journal %s", sched.id
            )
    db.session.commit()
    return {"posted": posted, "due": len(due)}

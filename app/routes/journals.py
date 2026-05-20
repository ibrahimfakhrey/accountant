from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from app import db
from app.models import JournalEntry, Account
from app.services.ledger import post_journal, reverse_journal, LedgerError

bp = Blueprint("journals", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    entries = JournalEntry.query.filter_by(company_id=g.active_company.id).order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(100).all()
    return render_template("journals/index.html", entries=entries)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    accounts = Account.query.filter_by(company_id=g.active_company.id, is_active=True).order_by(Account.code).all()

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        reference = request.form.get("reference", "").strip() or None
        entry_date_str = request.form.get("date") or date.today().isoformat()
        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
        currency = request.form.get("currency", g.active_company.base_currency)
        exchange_rate = float(request.form.get("exchange_rate", 1.0))

        account_ids = request.form.getlist("account_id[]")
        debits = request.form.getlist("debit[]")
        credits = request.form.getlist("credit[]")
        memos = request.form.getlist("memo[]")

        lines = []
        for i, aid in enumerate(account_ids):
            if not aid:
                continue
            d = float(debits[i] or 0)
            c = float(credits[i] or 0)
            if d == 0 and c == 0:
                continue
            lines.append({
                "account_id": int(aid),
                "debit": d,
                "credit": c,
                "memo": memos[i] if i < len(memos) else None,
            })

        try:
            post_journal(
                company_id=g.active_company.id,
                description=description,
                lines=lines,
                entry_date=entry_date,
                reference=reference,
                currency=currency,
                exchange_rate=exchange_rate,
                created_by=current_user.id,
            )
            flash("تم تسجيل القيد", "success")
            return redirect(url_for("journals.index"))
        except LedgerError as e:
            flash(str(e), "error")

    return render_template("journals/form.html", accounts=accounts)


@bp.route("/<int:entry_id>")
@login_required
def view(entry_id):
    entry = db.session.get(JournalEntry, entry_id)
    if not entry or entry.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("journals.index"))
    return render_template("journals/view.html", entry=entry)


@bp.route("/<int:entry_id>/reverse", methods=["POST"])
@login_required
def reverse(entry_id):
    entry = db.session.get(JournalEntry, entry_id)
    if not entry or entry.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("journals.index"))
    try:
        new_entry = reverse_journal(entry_id, created_by=current_user.id)
        flash(f"تم إنشاء قيد عكسي #{new_entry.id}", "success")
    except LedgerError as e:
        flash(str(e), "error")
    return redirect(url_for("journals.view", entry_id=entry_id))

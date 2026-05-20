from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from app import db
from app.models import Invoice, InvoiceItem, InvoiceStatus, Customer, Payment
from app.models.refund import RefundType
from app.services.invoicing import (
    post_invoice_to_ledger, record_payment, issue_refund, update_overdue_statuses
)
from app.services.ledger import LedgerError

bp = Blueprint("invoices", __name__)


def _next_number(company_id):
    last = Invoice.query.filter_by(company_id=company_id).order_by(Invoice.id.desc()).first()
    year = date.today().year
    n = (last.id if last else 0) + 1
    return f"{year}-{n:05d}"


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    update_overdue_statuses(g.active_company.id)
    status = request.args.get("status")
    q = Invoice.query.filter_by(company_id=g.active_company.id)
    if status:
        try:
            q = q.filter_by(status=InvoiceStatus[status])
        except KeyError:
            pass
    invoices = q.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all()
    return render_template("invoices/index.html", invoices=invoices, statuses=InvoiceStatus)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    customers = Customer.query.filter_by(company_id=g.active_company.id, is_active=True).order_by(Customer.name).all()
    if request.method == "POST":
        try:
            customer_id = int(request.form.get("customer_id"))
            issue_date = datetime.strptime(request.form.get("issue_date", date.today().isoformat()), "%Y-%m-%d").date()
            due_date = datetime.strptime(request.form.get("due_date", (date.today() + timedelta(days=30)).isoformat()), "%Y-%m-%d").date()
            tax_rate = float(request.form.get("tax_rate", g.active_company.vat_rate or 15))
            notes = request.form.get("notes", "")
            descriptions = request.form.getlist("item_description[]")
            quantities = request.form.getlist("item_quantity[]")
            unit_prices = request.form.getlist("item_unit_price[]")
            should_send = request.form.get("send") == "1"

            invoice = Invoice(
                company_id=g.active_company.id,
                number=_next_number(g.active_company.id),
                customer_id=customer_id,
                issue_date=issue_date,
                due_date=due_date,
                currency=g.active_company.base_currency,
                tax_rate=tax_rate,
                notes=notes,
                status=InvoiceStatus.DRAFT,
            )
            db.session.add(invoice)
            db.session.flush()
            for i, desc in enumerate(descriptions):
                if not desc.strip():
                    continue
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=desc.strip(),
                    quantity=float(quantities[i] or 1),
                    unit_price=float(unit_prices[i] or 0),
                )
                db.session.add(item)
            db.session.flush()
            # Reload items
            invoice.items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
            invoice.recalc()
            if should_send:
                invoice.status = InvoiceStatus.SENT
                post_invoice_to_ledger(invoice, created_by=current_user.id)
            db.session.commit()
            flash("تم إنشاء الفاتورة", "success")
            return redirect(url_for("invoices.view", invoice_id=invoice.id))
        except LedgerError as e:
            db.session.rollback()
            flash(str(e), "error")
        except Exception as e:
            db.session.rollback()
            flash(f"خطأ: {e}", "error")

    return render_template("invoices/form.html", customers=customers)


@bp.route("/<int:invoice_id>")
@login_required
def view(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("invoices.index"))
    return render_template("invoices/view.html", invoice=invoice, refund_types=RefundType)


@bp.route("/<int:invoice_id>/send", methods=["POST"])
@login_required
def send(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("invoices.index"))
    if invoice.status != InvoiceStatus.DRAFT:
        flash("الفاتورة ليست مسودة", "warning")
    else:
        try:
            invoice.status = InvoiceStatus.SENT
            post_invoice_to_ledger(invoice, created_by=current_user.id)
            flash("تم إرسال الفاتورة وتسجيل القيد", "success")
        except LedgerError as e:
            flash(str(e), "error")
    return redirect(url_for("invoices.view", invoice_id=invoice_id))


@bp.route("/<int:invoice_id>/pay", methods=["POST"])
@login_required
def pay(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("invoices.index"))
    try:
        amount = float(request.form.get("amount", 0))
        method = request.form.get("method", "cash")
        record_payment(invoice, amount, method=method, created_by=current_user.id)
        flash(f"تم تسجيل دفعة {amount:.2f}", "success")
    except LedgerError as e:
        flash(str(e), "error")
    return redirect(url_for("invoices.view", invoice_id=invoice_id))


@bp.route("/<int:invoice_id>/refund", methods=["POST"])
@login_required
def refund(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice or invoice.company_id != g.active_company.id:
        flash("غير موجود", "error")
        return redirect(url_for("invoices.index"))
    try:
        rtype = RefundType[request.form.get("type")]
        amount = request.form.get("amount")
        reason = request.form.get("reason", "")
        issue_refund(invoice, rtype, amount=amount, reason=reason, created_by=current_user.id)
        flash("تم تسجيل الاسترداد", "success")
    except (LedgerError, KeyError) as e:
        flash(str(e), "error")
    return redirect(url_for("invoices.view", invoice_id=invoice_id))

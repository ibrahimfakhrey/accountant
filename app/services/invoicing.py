"""Invoice posting logic — when an invoice is sent or paid, post journals automatically."""
from datetime import date
from app import db
from app.models import Invoice, InvoiceStatus, Payment, Account, Refund, RefundType, CreditNote, PaymentMethod
from app.services.ledger import post_journal, reverse_journal, get_account_by_code, LedgerError


def send_invoice_notification(invoice):
    """Wrapper: emails customer when invoice is sent. Safe — logs on failure."""
    try:
        from app.services.email import send_invoice_email
        return send_invoice_email(invoice, attach_pdf=True)
    except Exception:
        import logging
        logging.getLogger("ledgeros.invoicing").exception("Failed to send invoice email")
        return False


def post_invoice_to_ledger(invoice, created_by=None):
    """Dr Accounts Receivable / Cr Revenue + Cr VAT Payable."""
    ar = get_account_by_code(invoice.company_id, "1130")
    revenue = get_account_by_code(invoice.company_id, "4100")
    vat_payable = get_account_by_code(invoice.company_id, "2120")
    if not ar or not revenue:
        raise LedgerError("شجرة الحسابات الافتراضية ناقصة (1130 / 4100)")

    # Revenue is credited at the taxable_base (subtotal AFTER invoice-level discount).
    # This keeps the journal balanced: Dr AR (total) = Cr Revenue (net) + Cr VAT (tax).
    revenue_credit = float(invoice.taxable_base if invoice.taxable_base else invoice.subtotal)
    lines = [
        {"account_id": ar.id, "debit": float(invoice.total), "credit": 0, "memo": f"فاتورة {invoice.number}"},
        {"account_id": revenue.id, "debit": 0, "credit": revenue_credit, "memo": "إيراد (صافي بعد الخصم)"},
    ]
    if float(invoice.tax_amount or 0) > 0.001 and vat_payable:
        lines.append({
            "account_id": vat_payable.id,
            "debit": 0,
            "credit": float(invoice.tax_amount),
            "memo": "ضريبة قيمة مضافة",
        })

    return post_journal(
        company_id=invoice.company_id,
        description=f"فاتورة مبيعات #{invoice.number} — {invoice.customer.name}",
        lines=lines,
        entry_date=invoice.issue_date,
        reference=f"INV-{invoice.number}",
        currency=invoice.currency,
        created_by=created_by,
        source_type="invoice",
        source_id=invoice.id,
    )


def record_payment(invoice, amount, payment_date=None, method=None, payment_method_id=None, created_by=None, notify=True):
    """Record a payment posting Dr <method.account> / Cr AR. Resolves the receiving
    account either from a PaymentMethod row (preferred) or from the legacy
    'cash'/'bank' string.
    """
    amount = float(amount)
    if amount <= 0:
        raise LedgerError("المبلغ يجب أن يكون أكبر من صفر")
    if amount > invoice.balance + 0.01:
        raise LedgerError(f"المبلغ ({amount:.2f}) أكبر من الرصيد المتبقي ({invoice.balance:.2f})")

    pm = None
    receiving_account = None
    if payment_method_id:
        pm = db.session.get(PaymentMethod, int(payment_method_id))
        if not pm or pm.company_id != invoice.company_id or not pm.is_active:
            raise LedgerError("طريقة دفع غير صالحة")
        receiving_account = pm.account
        method_label = pm.name_ar or pm.name
    else:
        # Legacy fallback: 'cash' or 'bank'
        code = "1110" if (method or "cash") == "cash" else "1120"
        receiving_account = get_account_by_code(invoice.company_id, code)
        method_label = method or "cash"

    ar = get_account_by_code(invoice.company_id, "1130")
    if not receiving_account or not ar:
        raise LedgerError("حسابات النقدية / العملاء غير موجودة")

    entry = post_journal(
        company_id=invoice.company_id,
        description=f"تحصيل من {invoice.customer.name} — فاتورة #{invoice.number} ({method_label})",
        lines=[
            {"account_id": receiving_account.id, "debit": amount, "credit": 0},
            {"account_id": ar.id, "debit": 0, "credit": amount},
        ],
        entry_date=payment_date or date.today(),
        reference=f"PMT-{invoice.number}",
        currency=invoice.currency,
        created_by=created_by,
        source_type="payment",
        source_id=invoice.id,
    )

    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        payment_date=payment_date or date.today(),
        payment_method_id=pm.id if pm else None,
        method=(pm.name if pm else method),
        journal_entry_id=entry.id,
    )
    db.session.add(payment)

    invoice.paid_amount = float(invoice.paid_amount or 0) + amount
    is_full = invoice.paid_amount >= float(invoice.total) - 0.01
    if is_full:
        invoice.status = InvoiceStatus.PAID
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    db.session.commit()

    # Email notification — non-blocking, controlled by caller
    if notify:
        try:
            from app.services.email import send_payment_received_email
            send_payment_received_email(invoice, payment, is_full=is_full)
        except Exception:
            import logging
            logging.getLogger("ledgeros.invoicing").exception("Failed to send payment email")

    return payment


def issue_refund(invoice, refund_type, amount=None, reason=None, created_by=None, notify=False):
    """3 scenarios: FULL, PARTIAL, CREDIT_NOTE."""
    if refund_type == RefundType.FULL:
        amount = float(invoice.total)
    elif refund_type == RefundType.PARTIAL:
        if not amount or float(amount) <= 0:
            raise LedgerError("حدد مبلغ الاسترداد الجزئي")
        if float(amount) > float(invoice.paid_amount or 0) + 0.01:
            raise LedgerError("لا يمكن استرداد أكبر من المبلغ المدفوع فعلياً")
        amount = float(amount)
    elif refund_type == RefundType.CREDIT_NOTE:
        if not amount or float(amount) <= 0:
            raise LedgerError("حدد قيمة الـ Credit Note")
        amount = float(amount)

    revenue = get_account_by_code(invoice.company_id, "4100")
    vat_payable = get_account_by_code(invoice.company_id, "2120")
    ar = get_account_by_code(invoice.company_id, "1130")
    cash = get_account_by_code(invoice.company_id, "1110")

    # Split the refund amount across Revenue (net) and VAT Payable (tax)
    # using the same ratio as the original invoice. This mirrors the original
    # posting (Cr Revenue=subtotal + Cr VAT=tax) so VAT is reclaimed correctly.
    invoice_total = float(invoice.total or 0)
    invoice_tax = float(invoice.tax_amount or 0)
    if invoice_total > 0 and invoice_tax > 0 and vat_payable:
        tax_ratio = invoice_tax / invoice_total
        refund_tax = round(amount * tax_ratio, 2)
        refund_net = round(amount - refund_tax, 2)
    else:
        refund_tax = 0.0
        refund_net = amount

    debit_lines = [{"account_id": revenue.id, "debit": refund_net, "credit": 0, "memo": "عكس إيراد"}]
    if refund_tax > 0:
        debit_lines.append({
            "account_id": vat_payable.id,
            "debit": refund_tax,
            "credit": 0,
            "memo": "عكس ضريبة قيمة مضافة",
        })

    if refund_type == RefundType.CREDIT_NOTE:
        cn = CreditNote(
            company_id=invoice.company_id,
            customer_id=invoice.customer_id,
            invoice_id=invoice.id,
            amount=amount,
            reason=reason,
        )
        db.session.add(cn)
        entry = post_journal(
            company_id=invoice.company_id,
            description=f"Credit Note للعميل {invoice.customer.name} — فاتورة #{invoice.number}",
            lines=debit_lines + [
                {"account_id": ar.id, "debit": 0, "credit": amount, "memo": "رصيد دائن للعميل"},
            ],
            entry_date=date.today(),
            reference=f"CN-{invoice.number}",
            currency=invoice.currency,
            created_by=created_by,
            source_type="credit_note",
            source_id=invoice.id,
        )
    else:
        if float(invoice.paid_amount or 0) > 0:
            # Refund actual cash
            entry = post_journal(
                company_id=invoice.company_id,
                description=f"استرداد للعميل {invoice.customer.name} — فاتورة #{invoice.number}",
                lines=debit_lines + [
                    {"account_id": cash.id, "debit": 0, "credit": amount, "memo": "صرف نقدي للعميل"},
                ],
                entry_date=date.today(),
                reference=f"REF-{invoice.number}",
                currency=invoice.currency,
                created_by=created_by,
                source_type="refund",
                source_id=invoice.id,
            )
            invoice.paid_amount = float(invoice.paid_amount or 0) - amount
        else:
            # No payment yet — just reverse the receivable
            entry = post_journal(
                company_id=invoice.company_id,
                description=f"إلغاء فاتورة #{invoice.number}",
                lines=debit_lines + [
                    {"account_id": ar.id, "debit": 0, "credit": amount, "memo": "إلغاء الذمم"},
                ],
                entry_date=date.today(),
                reference=f"REF-{invoice.number}",
                currency=invoice.currency,
                created_by=created_by,
                source_type="refund",
                source_id=invoice.id,
            )

    refund = Refund(
        invoice_id=invoice.id,
        type=refund_type,
        amount=amount,
        reason=reason,
        journal_entry_id=entry.id,
    )
    db.session.add(refund)

    if refund_type == RefundType.FULL:
        invoice.status = InvoiceStatus.REFUNDED
    elif refund_type == RefundType.PARTIAL:
        invoice.status = InvoiceStatus.PARTIALLY_REFUNDED

    db.session.commit()

    if notify:
        try:
            from app.services.email import send_refund_email, send_credit_note_email
            if refund_type == RefundType.CREDIT_NOTE:
                # cn was created above; fetch latest matching credit note
                cn = CreditNote.query.filter_by(invoice_id=invoice.id).order_by(CreditNote.id.desc()).first()
                if cn:
                    send_credit_note_email(invoice, cn)
            else:
                send_refund_email(invoice, refund)
        except Exception:
            import logging
            logging.getLogger("ledgeros.invoicing").exception("refund email failed")
    return refund


def update_overdue_statuses(company_id):
    """Mark invoices as overdue if past due_date and unpaid."""
    today = date.today()
    invoices = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]),
        Invoice.due_date < today,
    ).all()
    for inv in invoices:
        inv.status = InvoiceStatus.OVERDUE
    db.session.commit()
    return len(invoices)

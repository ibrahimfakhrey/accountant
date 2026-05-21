"""Invoice posting logic — when an invoice is sent or paid, post journals automatically."""
from datetime import date
from app import db
from app.models import Invoice, InvoiceStatus, Payment, Account, Refund, RefundType, CreditNote
from app.services.ledger import post_journal, reverse_journal, get_account_by_code, LedgerError


def post_invoice_to_ledger(invoice, created_by=None):
    """Dr Accounts Receivable / Cr Revenue + Cr VAT Payable."""
    ar = get_account_by_code(invoice.company_id, "1130")
    revenue = get_account_by_code(invoice.company_id, "4100")
    vat_payable = get_account_by_code(invoice.company_id, "2120")
    if not ar or not revenue:
        raise LedgerError("شجرة الحسابات الافتراضية ناقصة (1130 / 4100)")

    lines = [
        {"account_id": ar.id, "debit": float(invoice.total), "credit": 0, "memo": f"فاتورة #{invoice.number}"},
        {"account_id": revenue.id, "debit": 0, "credit": float(invoice.subtotal), "memo": "إيراد"},
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


def record_payment(invoice, amount, payment_date=None, method="cash", created_by=None):
    """Record a payment: Dr Cash/Bank / Cr Accounts Receivable. Updates invoice status."""
    amount = float(amount)
    if amount <= 0:
        raise LedgerError("المبلغ يجب أن يكون أكبر من صفر")
    if amount > invoice.balance + 0.01:
        raise LedgerError(f"المبلغ ({amount:.2f}) أكبر من الرصيد المتبقي ({invoice.balance:.2f})")

    cash_code = "1110" if method == "cash" else "1120"
    cash = get_account_by_code(invoice.company_id, cash_code)
    ar = get_account_by_code(invoice.company_id, "1130")
    if not cash or not ar:
        raise LedgerError("حسابات النقدية / العملاء غير موجودة")

    entry = post_journal(
        company_id=invoice.company_id,
        description=f"تحصيل من {invoice.customer.name} — فاتورة #{invoice.number}",
        lines=[
            {"account_id": cash.id, "debit": amount, "credit": 0},
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
        method=method,
        journal_entry_id=entry.id,
    )
    db.session.add(payment)

    invoice.paid_amount = float(invoice.paid_amount or 0) + amount
    if invoice.paid_amount >= float(invoice.total) - 0.01:
        invoice.status = InvoiceStatus.PAID
    else:
        invoice.status = InvoiceStatus.PARTIALLY_PAID
    db.session.commit()
    return payment


def issue_refund(invoice, refund_type, amount=None, reason=None, created_by=None):
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

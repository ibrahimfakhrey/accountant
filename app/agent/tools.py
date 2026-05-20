"""Tools exposed to the AI accountant agent (Claude tool use)."""
from datetime import datetime, date, timedelta
from app import db
from app.models import (
    Account, Customer, Vendor, Invoice, InvoiceItem, InvoiceStatus,
    Employee, FixedAsset, JournalEntry,
)
from app.services.ledger import post_journal, get_account_by_code, LedgerError
from app.services.invoicing import post_invoice_to_ledger, record_payment
from app.services.reports import balance_sheet, income_statement, cash_flow, aging_report, dashboard_metrics


TOOL_SCHEMAS = [
    {
        "name": "list_accounts",
        "description": "اعرض شجرة الحسابات (Chart of Accounts) للشركة الحالية. استخدمها للبحث عن account_id قبل إنشاء قيد.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "نص للبحث في اسم أو كود الحساب (اختياري)"}
            },
        },
    },
    {
        "name": "list_customers",
        "description": "اعرض كل العملاء في الشركة الحالية مع أرصدتهم.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_customer",
        "description": "أضف عميل جديد.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "tax_number": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "create_journal_entry",
        "description": "سجّل قيد محاسبي مزدوج. مجموع المدين يجب أن يساوي مجموع الدائن.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "وصف القيد"},
                "entry_date": {"type": "string", "description": "تاريخ القيد بصيغة YYYY-MM-DD (افتراضي اليوم)"},
                "reference": {"type": "string", "description": "رقم مرجعي (اختياري)"},
                "lines": {
                    "type": "array",
                    "description": "سطور القيد، كل سطر فيه account_id ومبلغ مدين أو دائن",
                    "items": {
                        "type": "object",
                        "properties": {
                            "account_id": {"type": "integer"},
                            "debit": {"type": "number"},
                            "credit": {"type": "number"},
                            "memo": {"type": "string"},
                        },
                        "required": ["account_id"],
                    },
                },
            },
            "required": ["description", "lines"],
        },
    },
    {
        "name": "create_invoice",
        "description": "أنشئ فاتورة جديدة للعميل وأرسلها (تسجل قيد محاسبي تلقائياً).",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number"},
                        },
                        "required": ["description", "quantity", "unit_price"],
                    },
                },
                "due_days": {"type": "integer", "description": "أيام الاستحقاق من اليوم (افتراضي 30)"},
                "tax_rate": {"type": "number", "description": "نسبة الضريبة % (افتراضي حسب الشركة)"},
                "send": {"type": "boolean", "description": "إرسال فوري وتسجيل قيد (افتراضي true)"},
            },
            "required": ["customer_id", "items"],
        },
    },
    {
        "name": "record_invoice_payment",
        "description": "سجّل دفعة على فاتورة.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "integer"},
                "amount": {"type": "number"},
                "method": {"type": "string", "enum": ["cash", "bank"], "description": "افتراضي cash"},
            },
            "required": ["invoice_id", "amount"],
        },
    },
    {
        "name": "get_invoice",
        "description": "اعرض تفاصيل فاتورة بما فيها الحالة والرصيد.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "integer"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "run_report",
        "description": "شغّل تقرير مالي.",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["balance_sheet", "income_statement", "cash_flow", "aging", "dashboard"],
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD (افتراضي اليوم)"},
            },
            "required": ["type"],
        },
    },
    {
        "name": "explain_concept",
        "description": "اشرح مفهوم محاسبي للمستخدم. استخدمها لو المستخدم سأل سؤال نظري.",
        "input_schema": {
            "type": "object",
            "properties": {"concept": {"type": "string"}},
            "required": ["concept"],
        },
    },
]


def _parse_date(s, default=None):
    if not s:
        return default or date.today()
    if isinstance(s, date):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()


def execute_tool(name, args, company_id, user_id):
    """Dispatch a tool call. Returns a JSON-serializable result dict."""
    try:
        if name == "list_accounts":
            q = Account.query.filter_by(company_id=company_id, is_active=True)
            search = args.get("search", "").strip()
            if search:
                like = f"%{search}%"
                q = q.filter(db.or_(Account.code.ilike(like), Account.name.ilike(like), Account.name_ar.ilike(like)))
            accounts = q.order_by(Account.code).limit(50).all()
            return {
                "accounts": [
                    {"id": a.id, "code": a.code, "name": a.name, "name_ar": a.name_ar, "type": a.type.value, "balance": round(a.balance, 2)}
                    for a in accounts
                ]
            }

        if name == "list_customers":
            customers = Customer.query.filter_by(company_id=company_id, is_active=True).all()
            return {
                "customers": [
                    {"id": c.id, "name": c.name, "email": c.email, "phone": c.phone, "balance": round(c.balance, 2)}
                    for c in customers
                ]
            }

        if name == "create_customer":
            c = Customer(
                company_id=company_id,
                name=args["name"],
                email=args.get("email", ""),
                phone=args.get("phone", ""),
                tax_number=args.get("tax_number", ""),
            )
            db.session.add(c)
            db.session.commit()
            return {"ok": True, "customer_id": c.id, "name": c.name}

        if name == "create_journal_entry":
            entry = post_journal(
                company_id=company_id,
                description=args["description"],
                lines=args["lines"],
                entry_date=_parse_date(args.get("entry_date")),
                reference=args.get("reference"),
                created_by=user_id,
            )
            return {
                "ok": True,
                "entry_id": entry.id,
                "total_debit": entry.total_debit,
                "total_credit": entry.total_credit,
            }

        if name == "create_invoice":
            from app.models import Company
            company = db.session.get(Company, company_id)
            from app.routes.invoices import _next_number
            due_days = args.get("due_days", 30)
            tax_rate = args.get("tax_rate", float(company.vat_rate or 15))
            invoice = Invoice(
                company_id=company_id,
                number=_next_number(company_id),
                customer_id=args["customer_id"],
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=due_days),
                currency=company.base_currency,
                tax_rate=tax_rate,
                status=InvoiceStatus.DRAFT,
            )
            db.session.add(invoice)
            db.session.flush()
            for it in args["items"]:
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=it["description"],
                    quantity=it["quantity"],
                    unit_price=it["unit_price"],
                )
                db.session.add(item)
            db.session.flush()
            invoice.items = InvoiceItem.query.filter_by(invoice_id=invoice.id).all()
            invoice.recalc()
            if args.get("send", True):
                invoice.status = InvoiceStatus.SENT
                post_invoice_to_ledger(invoice, created_by=user_id)
            db.session.commit()
            return {
                "ok": True,
                "invoice_id": invoice.id,
                "number": invoice.number,
                "total": float(invoice.total),
                "tax_amount": float(invoice.tax_amount),
                "status": invoice.status.value,
            }

        if name == "record_invoice_payment":
            inv = db.session.get(Invoice, args["invoice_id"])
            if not inv or inv.company_id != company_id:
                return {"error": "الفاتورة غير موجودة"}
            pmt = record_payment(inv, args["amount"], method=args.get("method", "cash"), created_by=user_id)
            return {
                "ok": True,
                "payment_id": pmt.id,
                "invoice_status": inv.status.value,
                "remaining_balance": inv.balance,
            }

        if name == "get_invoice":
            inv = db.session.get(Invoice, args["invoice_id"])
            if not inv or inv.company_id != company_id:
                return {"error": "غير موجود"}
            return {
                "invoice_id": inv.id,
                "number": inv.number,
                "customer": inv.customer.name,
                "issue_date": str(inv.issue_date),
                "due_date": str(inv.due_date),
                "subtotal": float(inv.subtotal),
                "tax_amount": float(inv.tax_amount),
                "total": float(inv.total),
                "paid_amount": float(inv.paid_amount or 0),
                "balance": inv.balance,
                "status": inv.status.value,
                "items": [
                    {"description": i.description, "quantity": float(i.quantity), "unit_price": float(i.unit_price)}
                    for i in inv.items
                ],
            }

        if name == "run_report":
            rtype = args["type"]
            start = _parse_date(args.get("start_date"), date.today().replace(day=1))
            end = _parse_date(args.get("end_date"), date.today())
            if rtype == "balance_sheet":
                return balance_sheet(company_id, as_of=end)
            if rtype == "income_statement":
                return income_statement(company_id, start_date=start, end_date=end)
            if rtype == "cash_flow":
                return cash_flow(company_id, start_date=start, end_date=end)
            if rtype == "aging":
                return aging_report(company_id, as_of=end)
            if rtype == "dashboard":
                return dashboard_metrics(company_id)

        if name == "explain_concept":
            # The agent itself does the explaining; this just confirms which concept.
            return {"concept": args["concept"], "instruction": "اشرح هذا المفهوم بالعربية بشكل مبسط وعملي"}

        return {"error": f"أداة غير معروفة: {name}"}
    except LedgerError as e:
        db.session.rollback()
        return {"error": str(e)}
    except Exception as e:
        db.session.rollback()
        return {"error": f"خطأ في تنفيذ الأداة: {e}"}

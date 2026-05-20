"""Financial report generators: Balance Sheet, Income Statement, Cash Flow."""
from datetime import date
from sqlalchemy import func, and_
from app import db
from app.models import Account, AccountType, JournalLine, JournalEntry


def _account_balance(account_id, start_date=None, end_date=None):
    q = db.session.query(
        func.coalesce(func.sum(JournalLine.debit_base), 0),
        func.coalesce(func.sum(JournalLine.credit_base), 0),
    ).select_from(JournalLine).join(JournalEntry).filter(JournalLine.account_id == account_id)
    if start_date:
        q = q.filter(JournalEntry.date >= start_date)
    if end_date:
        q = q.filter(JournalEntry.date <= end_date)
    debit, credit = q.first()
    return float(debit or 0), float(credit or 0)


def _signed_balance(account, debit, credit):
    if account.normal_side.value == "DEBIT":
        return debit - credit
    return credit - debit


def balance_sheet(company_id, as_of=None):
    """Snapshot of Assets, Liabilities, Equity as of a date."""
    as_of = as_of or date.today()
    accounts = Account.query.filter_by(company_id=company_id, is_active=True).all()

    result = {"assets": [], "liabilities": [], "equity": [], "as_of": as_of}
    totals = {"assets": 0.0, "liabilities": 0.0, "equity": 0.0}

    for acc in accounts:
        debit, credit = _account_balance(acc.id, end_date=as_of)
        bal = _signed_balance(acc, debit, credit)
        if abs(bal) < 0.01 and not acc.children:
            continue
        item = {"code": acc.code, "name": acc.name_ar or acc.name, "balance": bal}
        if acc.type == AccountType.ASSET:
            result["assets"].append(item)
            totals["assets"] += bal
        elif acc.type == AccountType.LIABILITY:
            result["liabilities"].append(item)
            totals["liabilities"] += bal
        elif acc.type == AccountType.EQUITY:
            result["equity"].append(item)
            totals["equity"] += bal

    net_income = _net_income(company_id, end_date=as_of)
    if abs(net_income) > 0.01:
        result["equity"].append({
            "code": "RE", "name": "صافي الربح للفترة", "balance": net_income
        })
        totals["equity"] += net_income

    result["totals"] = totals
    result["total_liab_equity"] = totals["liabilities"] + totals["equity"]
    result["balanced"] = abs(totals["assets"] - result["total_liab_equity"]) < 0.01
    return result


def _net_income(company_id, start_date=None, end_date=None):
    revenue = 0.0
    expense = 0.0
    accounts = Account.query.filter_by(company_id=company_id).all()
    for acc in accounts:
        d, c = _account_balance(acc.id, start_date=start_date, end_date=end_date)
        bal = _signed_balance(acc, d, c)
        if acc.type == AccountType.REVENUE:
            revenue += bal
        elif acc.type == AccountType.EXPENSE:
            expense += bal
    return revenue - expense


def income_statement(company_id, start_date=None, end_date=None):
    end_date = end_date or date.today()
    accounts = Account.query.filter_by(company_id=company_id, is_active=True).all()

    result = {
        "revenue": [], "expenses": [],
        "start_date": start_date, "end_date": end_date,
    }
    total_revenue = 0.0
    total_expense = 0.0

    for acc in accounts:
        d, c = _account_balance(acc.id, start_date=start_date, end_date=end_date)
        bal = _signed_balance(acc, d, c)
        if abs(bal) < 0.01:
            continue
        item = {"code": acc.code, "name": acc.name_ar or acc.name, "balance": bal}
        if acc.type == AccountType.REVENUE:
            result["revenue"].append(item)
            total_revenue += bal
        elif acc.type == AccountType.EXPENSE:
            result["expenses"].append(item)
            total_expense += bal

    result["total_revenue"] = total_revenue
    result["total_expense"] = total_expense
    result["net_income"] = total_revenue - total_expense
    return result


def cash_flow(company_id, start_date=None, end_date=None):
    """Simplified Cash Flow using cash account movements categorized."""
    end_date = end_date or date.today()
    cash_codes = ["1110", "1120"]
    cash_accounts = Account.query.filter(
        Account.company_id == company_id, Account.code.in_(cash_codes)
    ).all()
    cash_ids = [a.id for a in cash_accounts]

    operating = 0.0
    investing = 0.0
    financing = 0.0

    if cash_ids:
        entries = (
            JournalEntry.query.join(JournalLine)
            .filter(
                JournalEntry.company_id == company_id,
                JournalLine.account_id.in_(cash_ids),
            )
        )
        if start_date:
            entries = entries.filter(JournalEntry.date >= start_date)
        if end_date:
            entries = entries.filter(JournalEntry.date <= end_date)

        for entry in entries.distinct():
            cash_flow_amt = 0.0
            other_type = None
            for line in entry.lines:
                if line.account_id in cash_ids:
                    cash_flow_amt += float(line.debit_base) - float(line.credit_base)
                else:
                    other_type = line.account.type

            if other_type == AccountType.ASSET and entry.source_type == "asset_purchase":
                investing += cash_flow_amt
            elif other_type == AccountType.EQUITY or other_type == AccountType.LIABILITY:
                financing += cash_flow_amt
            else:
                operating += cash_flow_amt

    return {
        "operating": operating,
        "investing": investing,
        "financing": financing,
        "net_change": operating + investing + financing,
        "start_date": start_date,
        "end_date": end_date,
    }


def aging_report(company_id, as_of=None):
    """Customer aging report: 0-30, 31-60, 61-90, 90+ days overdue."""
    from app.models import Invoice, InvoiceStatus, Customer
    as_of = as_of or date.today()
    customers = Customer.query.filter_by(company_id=company_id, is_active=True).all()
    rows = []
    totals = {"current": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d90plus": 0.0, "total": 0.0}
    for c in customers:
        buckets = {"current": 0.0, "d30": 0.0, "d60": 0.0, "d90": 0.0, "d90plus": 0.0}
        for inv in c.invoices:
            if inv.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED, InvoiceStatus.REFUNDED):
                continue
            bal = inv.balance
            if bal <= 0.01:
                continue
            days_overdue = (as_of - inv.due_date).days
            if days_overdue <= 0:
                buckets["current"] += bal
            elif days_overdue <= 30:
                buckets["d30"] += bal
            elif days_overdue <= 60:
                buckets["d60"] += bal
            elif days_overdue <= 90:
                buckets["d90"] += bal
            else:
                buckets["d90plus"] += bal
        total = sum(buckets.values())
        if total > 0.01:
            rows.append({"customer": c.name, "customer_id": c.id, **buckets, "total": total})
            for k in buckets:
                totals[k] += buckets[k]
            totals["total"] += total
    return {"rows": rows, "totals": totals, "as_of": as_of}


def dashboard_metrics(company_id):
    """Key metrics for the dashboard."""
    from app.models import Invoice, InvoiceStatus
    today = date.today()
    start_month = today.replace(day=1)
    prev_month_end = start_month.replace(day=1)
    from calendar import monthrange
    prev_month_end = (start_month.replace(day=1).replace(day=1))
    # Just compute current month
    inc = income_statement(company_id, start_date=start_month, end_date=today)
    bs = balance_sheet(company_id, as_of=today)
    cash_accounts = Account.query.filter(
        Account.company_id == company_id, Account.code.in_(["1110", "1120"])
    ).all()
    cash_position = sum(float(a.balance) for a in cash_accounts)

    unpaid = Invoice.query.filter(
        Invoice.company_id == company_id,
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE])
    ).all()
    unpaid_total = sum(i.balance for i in unpaid)
    overdue = [i for i in unpaid if i.due_date < today]
    overdue_total = sum(i.balance for i in overdue)

    ap_account = Account.query.filter_by(company_id=company_id, code="2110").first()
    accounts_payable = float(ap_account.balance) if ap_account else 0.0

    total_assets = bs["totals"]["assets"]
    total_liab = bs["totals"]["liabilities"]
    total_equity = bs["totals"]["equity"]
    debt_to_equity = (total_liab / total_equity) if total_equity > 0.01 else 0.0

    current_assets_codes = ["1110", "1120", "1130", "1140", "1150"]
    current_liab_codes = ["2110", "2120", "2130", "2140"]
    current_assets = sum(
        float(a.balance) for a in Account.query.filter(
            Account.company_id == company_id, Account.code.in_(current_assets_codes)
        ).all()
    )
    current_liab = sum(
        float(a.balance) for a in Account.query.filter(
            Account.company_id == company_id, Account.code.in_(current_liab_codes)
        ).all()
    )
    current_ratio = (current_assets / current_liab) if current_liab > 0.01 else 0.0

    return {
        "total_revenue": inc["total_revenue"],
        "total_expenses": inc["total_expense"],
        "net_profit": inc["net_income"],
        "cash_position": cash_position,
        "unpaid_invoices": {"count": len(unpaid), "total": unpaid_total},
        "overdue_invoices": {"count": len(overdue), "total": overdue_total},
        "accounts_payable": accounts_payable,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
    }

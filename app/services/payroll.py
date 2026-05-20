"""Payroll processing — generate monthly run + journal entry."""
from calendar import month_name
from app import db
from app.models import Employee, PayrollRun, PayrollLine
from app.services.ledger import post_journal, get_account_by_code, LedgerError


def run_payroll(company_id, year, month, created_by=None):
    existing = PayrollRun.query.filter_by(
        company_id=company_id, period_year=year, period_month=month
    ).first()
    if existing:
        raise LedgerError(f"كشف رواتب {month}/{year} موجود بالفعل")

    employees = Employee.query.filter_by(company_id=company_id, is_active=True).all()
    if not employees:
        raise LedgerError("لا يوجد موظفين نشطين")

    run = PayrollRun(company_id=company_id, period_year=year, period_month=month)
    db.session.add(run)
    db.session.flush()

    total_gross = 0.0
    total_net = 0.0
    for emp in employees:
        basic = float(emp.basic_salary or 0)
        allowances = float(emp.allowances or 0)
        deductions = float(emp.deductions or 0)
        net = basic + allowances - deductions
        line = PayrollLine(
            run_id=run.id,
            employee_id=emp.id,
            basic=basic,
            allowances=allowances,
            deductions=deductions,
            net=net,
        )
        db.session.add(line)
        total_gross += basic + allowances
        total_net += net

    salary_expense = get_account_by_code(company_id, "5210")
    salary_payable = get_account_by_code(company_id, "2130")
    if not salary_expense or not salary_payable:
        raise LedgerError("حسابات الرواتب غير موجودة في شجرة الحسابات")

    entry = post_journal(
        company_id=company_id,
        description=f"رواتب شهر {month}/{year}",
        lines=[
            {"account_id": salary_expense.id, "debit": total_net, "credit": 0},
            {"account_id": salary_payable.id, "debit": 0, "credit": total_net},
        ],
        reference=f"PAYROLL-{year}-{month:02d}",
        created_by=created_by,
        source_type="payroll",
        source_id=run.id,
    )
    run.total_gross = total_gross
    run.total_net = total_net
    run.journal_entry_id = entry.id
    db.session.commit()
    return run

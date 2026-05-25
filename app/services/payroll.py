"""Payroll processing — generates monthly run + journal entry.

Variable inputs (working days, overtime, absence/late/advance, bonus) are passed
per-employee. They are stored on the PayrollLine and reset implicitly each month
because each run gets a fresh set of lines.

Prorated salary uses a 30-day basis (Gulf standard): basic/30 × working_days.
SUSPENDED and TERMINATED employees are excluded.
"""
from datetime import date
from app import db
from app.models import Employee, EmployeeStatus, PayrollRun, PayrollLine
from app.services.ledger import post_journal, get_account_by_code, LedgerError
from app.services.numbering import next_number


def run_payroll(company_id, year, month, line_inputs=None, created_by=None, send_emails=True):
    """Execute a payroll run.

    line_inputs: optional dict keyed by employee_id with overrides:
        {emp_id: {working_days, overtime, bonus, absence, late, advance}}
        Missing employees use defaults (30 days, no variable amounts).
    """
    existing = PayrollRun.query.filter_by(
        company_id=company_id, period_year=year, period_month=month
    ).first()
    if existing:
        raise LedgerError(f"كشف رواتب {month}/{year} موجود بالفعل")

    employees = Employee.query.filter_by(company_id=company_id, status=EmployeeStatus.ACTIVE).all()
    if not employees:
        raise LedgerError("لا يوجد موظفين نشطين")

    run = PayrollRun(
        company_id=company_id,
        number=next_number(company_id, "PAYROLL"),
        period_year=year,
        period_month=month,
    )
    db.session.add(run)
    db.session.flush()

    line_inputs = line_inputs or {}
    total_gross = 0.0
    total_net = 0.0
    lines_created = []
    for emp in employees:
        inputs = line_inputs.get(emp.id, {})
        working_days = int(inputs.get("working_days", 30))
        overtime = float(inputs.get("overtime", 0) or 0)
        bonus = float(inputs.get("bonus", 0) or 0)
        absence = float(inputs.get("absence", 0) or 0)
        late = float(inputs.get("late", 0) or 0)
        advance = float(inputs.get("advance", 0) or 0)

        basic_full = float(emp.basic_salary or 0)
        prorated_basic = (basic_full / 30.0) * max(0, min(working_days, 30))
        allowances = float(emp.allowances or 0)
        fixed_deductions = float(emp.deductions or 0)

        gross = prorated_basic + allowances + overtime + bonus
        total_deductions = fixed_deductions + absence + late + advance
        net = gross - total_deductions

        line = PayrollLine(
            run_id=run.id,
            employee_id=emp.id,
            working_days=working_days,
            basic=round(prorated_basic, 2),
            allowances=allowances,
            overtime=overtime,
            bonus=bonus,
            deductions=fixed_deductions,
            absence_deduction=absence,
            late_deduction=late,
            advance_deduction=advance,
            net=round(net, 2),
        )
        db.session.add(line)
        lines_created.append((emp, line))
        total_gross += gross
        total_net += net

    salary_expense = get_account_by_code(company_id, "5210")
    salary_payable = get_account_by_code(company_id, "2130")
    if not salary_expense or not salary_payable:
        raise LedgerError("حسابات الرواتب غير موجودة في شجرة الحسابات")

    entry = post_journal(
        company_id=company_id,
        description=f"رواتب شهر {month}/{year}",
        lines=[
            {"account_id": salary_expense.id, "debit": round(total_net, 2), "credit": 0},
            {"account_id": salary_payable.id, "debit": 0, "credit": round(total_net, 2)},
        ],
        reference=f"PAYROLL-{year}-{month:02d}",
        created_by=created_by,
        source_type="payroll",
        source_id=run.id,
    )
    run.total_gross = round(total_gross, 2)
    run.total_net = round(total_net, 2)
    run.journal_entry_id = entry.id
    db.session.commit()

    # Email payslips — non-blocking
    if send_emails:
        try:
            from app.services.email import send_payslip_email
            from app.services.export import export_payslip_pdf
            for emp, line in lines_created:
                if emp.email:
                    try:
                        pdf = export_payslip_pdf(emp, line, run).getvalue()
                    except Exception:
                        pdf = None
                    send_payslip_email(emp, line, run, pdf_bytes=pdf)
        except Exception:
            import logging
            logging.getLogger("ledgeros.payroll").exception("Failed to send payslips")

    return run


def terminate_employee(employee, reason, termination_date=None, notes=None):
    employee.status = EmployeeStatus.TERMINATED
    employee.is_active = False
    employee.termination_date = termination_date or date.today()
    employee.termination_reason = reason
    employee.termination_notes = notes
    db.session.commit()
    return employee

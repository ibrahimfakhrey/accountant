from datetime import date, datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, g, send_file
from flask_login import login_required, current_user
from app import db
from app.models import (
    Employee, EmployeeStatus, ContractType, TerminationReason,
    PayrollRun, PayrollLine,
)
from app.services.payroll import run_payroll, terminate_employee
from app.services.ledger import LedgerError
from app.services.numbering import next_number

bp = Blueprint("payroll", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))

    status_filter = request.args.get("status", "ACTIVE")
    search = (request.args.get("search") or "").strip()

    q = Employee.query.filter_by(company_id=g.active_company.id)
    if status_filter and status_filter != "ALL":
        try:
            q = q.filter_by(status=EmployeeStatus[status_filter])
        except KeyError:
            pass
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(Employee.name.ilike(like), Employee.job_title.ilike(like)))
    employees = q.order_by(Employee.name).all()

    runs = PayrollRun.query.filter_by(company_id=g.active_company.id).order_by(
        PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
    ).limit(12).all()
    return render_template(
        "payroll/index.html",
        employees=employees, runs=runs,
        statuses=EmployeeStatus, status_filter=status_filter, search=search,
    )


@bp.route("/employees/new", methods=["GET", "POST"])
@login_required
def new_employee():
    if request.method == "POST":
        try:
            ct_str = request.form.get("contract_type", "FULL_TIME")
            start_str = request.form.get("start_date") or date.today().isoformat()
            emp = Employee(
                company_id=g.active_company.id,
                employee_number=next_number(g.active_company.id, "EMPLOYEE"),
                name=request.form.get("name", "").strip(),
                email=request.form.get("email", "").strip(),
                phone=request.form.get("phone", "").strip(),
                job_title=request.form.get("job_title", "").strip(),
                start_date=datetime.strptime(start_str, "%Y-%m-%d").date(),
                contract_type=ContractType[ct_str],
                status=EmployeeStatus.ACTIVE,
                basic_salary=float(request.form.get("basic_salary", 0)),
                allowances=float(request.form.get("allowances", 0)),
                deductions=float(request.form.get("deductions", 0)),
            )
            if not emp.name:
                raise ValueError("اسم الموظف مطلوب")
            db.session.add(emp)
            db.session.commit()
            flash(f"تم إضافة الموظف {emp.employee_number}", "success")
            return redirect(url_for("payroll.employee_profile", employee_id=emp.id))
        except (ValueError, KeyError) as e:
            flash(str(e), "error")
    return render_template("payroll/employee_form.html", contract_types=ContractType)


@bp.route("/employees/<int:employee_id>")
@login_required
def employee_profile(employee_id):
    emp = db.session.get(Employee, employee_id)
    if not emp or emp.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    payslips = PayrollLine.query.filter_by(employee_id=emp.id).join(PayrollRun).order_by(
        PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
    ).all()
    return render_template(
        "payroll/employee_profile.html",
        employee=emp, payslips=payslips,
        termination_reasons=TerminationReason,
    )


@bp.route("/employees/<int:employee_id>/terminate", methods=["POST"])
@login_required
def terminate(employee_id):
    emp = db.session.get(Employee, employee_id)
    if not emp or emp.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    try:
        reason = TerminationReason[request.form.get("reason", "OTHER")]
        notes = request.form.get("notes", "")
        td_str = request.form.get("termination_date") or date.today().isoformat()
        td = datetime.strptime(td_str, "%Y-%m-%d").date()
        terminate_employee(emp, reason, termination_date=td, notes=notes)
        flash("تم تسجيل إنهاء العقد", "success")
    except (KeyError, ValueError) as e:
        flash(str(e), "error")
    return redirect(url_for("payroll.employee_profile", employee_id=emp.id))


@bp.route("/run", methods=["GET", "POST"])
@login_required
def run():
    """GET: show form with per-employee variable inputs. POST: execute."""
    if not g.active_company:
        return redirect(url_for("companies.new"))

    employees = Employee.query.filter_by(
        company_id=g.active_company.id, status=EmployeeStatus.ACTIVE
    ).order_by(Employee.name).all()

    if request.method == "POST":
        today = date.today()
        year = int(request.form.get("year", today.year))
        month = int(request.form.get("month", today.month))
        send_emails = request.form.get("send_emails") == "1"

        line_inputs = {}
        for emp in employees:
            line_inputs[emp.id] = {
                "working_days": int(request.form.get(f"working_days_{emp.id}", 30) or 30),
                "overtime": float(request.form.get(f"overtime_{emp.id}", 0) or 0),
                "bonus": float(request.form.get(f"bonus_{emp.id}", 0) or 0),
                "absence": float(request.form.get(f"absence_{emp.id}", 0) or 0),
                "late": float(request.form.get(f"late_{emp.id}", 0) or 0),
                "advance": float(request.form.get(f"advance_{emp.id}", 0) or 0),
            }
        try:
            pr = run_payroll(
                g.active_company.id, year, month,
                line_inputs=line_inputs, created_by=current_user.id,
                send_emails=send_emails,
            )
            flash(f"تم تنفيذ كشف {pr.number} — صافي {pr.total_net:.2f}", "success")
            return redirect(url_for("payroll.view_run", run_id=pr.id))
        except LedgerError as e:
            flash(str(e), "error")

    today = date.today()
    return render_template(
        "payroll/run_form.html",
        employees=employees, today=today,
    )


@bp.route("/run/<int:run_id>")
@login_required
def view_run(run_id):
    pr = db.session.get(PayrollRun, run_id)
    if not pr or pr.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    return render_template("payroll/run.html", run=pr)


@bp.route("/run/<int:run_id>/export/<fmt>")
@login_required
def export_run(run_id, fmt):
    pr = db.session.get(PayrollRun, run_id)
    if not pr or pr.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    from app.services.export import export_payroll_run_pdf, export_payroll_run_excel
    if fmt == "pdf":
        buf = export_payroll_run_pdf(pr)
        return send_file(buf, mimetype="application/pdf",
                         download_name=f"payroll-{pr.period_year}-{pr.period_month:02d}.pdf",
                         as_attachment=True)
    if fmt == "excel":
        buf = export_payroll_run_excel(pr)
        return send_file(buf,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         download_name=f"payroll-{pr.period_year}-{pr.period_month:02d}.xlsx",
                         as_attachment=True)
    return redirect(url_for("payroll.view_run", run_id=run_id))


@bp.route("/run/<int:run_id>/line/<int:line_id>/payslip.pdf")
@login_required
def payslip_pdf(run_id, line_id):
    line = db.session.get(PayrollLine, line_id)
    if not line or line.run_id != run_id:
        return redirect(url_for("payroll.index"))
    pr = db.session.get(PayrollRun, run_id)
    if pr.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    from app.services.export import export_payslip_pdf
    buf = export_payslip_pdf(line.employee, line, pr)
    return send_file(buf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"payslip-{line.employee.employee_number}-{pr.period_year}-{pr.period_month:02d}.pdf")

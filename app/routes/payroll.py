from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from app import db
from app.models import Employee, PayrollRun
from app.services.payroll import run_payroll
from app.services.ledger import LedgerError

bp = Blueprint("payroll", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    employees = Employee.query.filter_by(company_id=g.active_company.id).order_by(Employee.name).all()
    runs = PayrollRun.query.filter_by(company_id=g.active_company.id).order_by(
        PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
    ).all()
    return render_template("payroll/index.html", employees=employees, runs=runs)


@bp.route("/employees/new", methods=["GET", "POST"])
@login_required
def new_employee():
    if request.method == "POST":
        try:
            emp = Employee(
                company_id=g.active_company.id,
                name=request.form.get("name", "").strip(),
                email=request.form.get("email", "").strip(),
                job_title=request.form.get("job_title", "").strip(),
                basic_salary=float(request.form.get("basic_salary", 0)),
                allowances=float(request.form.get("allowances", 0)),
                deductions=float(request.form.get("deductions", 0)),
            )
            if not emp.name:
                raise ValueError("اسم الموظف مطلوب")
            db.session.add(emp)
            db.session.commit()
            flash("تم إضافة الموظف", "success")
            return redirect(url_for("payroll.index"))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("payroll/employee_form.html")


@bp.route("/run", methods=["POST"])
@login_required
def run():
    today = date.today()
    year = int(request.form.get("year", today.year))
    month = int(request.form.get("month", today.month))
    try:
        pr = run_payroll(g.active_company.id, year, month, created_by=current_user.id)
        flash(f"تم تنفيذ كشف رواتب {month}/{year} — صافي {pr.total_net:.2f}", "success")
    except LedgerError as e:
        flash(str(e), "error")
    return redirect(url_for("payroll.index"))


@bp.route("/run/<int:run_id>")
@login_required
def view_run(run_id):
    pr = db.session.get(PayrollRun, run_id)
    if not pr or pr.company_id != g.active_company.id:
        return redirect(url_for("payroll.index"))
    return render_template("payroll/run.html", run=pr)

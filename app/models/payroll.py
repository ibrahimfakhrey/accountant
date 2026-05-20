from datetime import datetime, date
from app import db


class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150))
    job_title = db.Column(db.String(100))
    basic_salary = db.Column(db.Numeric(15, 2), default=0)
    allowances = db.Column(db.Numeric(15, 2), default=0)
    deductions = db.Column(db.Numeric(15, 2), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company", backref=db.backref("employees", lazy="dynamic"))


class PayrollRun(db.Model):
    __tablename__ = "payroll_runs"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    period_year = db.Column(db.Integer, nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    total_gross = db.Column(db.Numeric(15, 2), default=0)
    total_net = db.Column(db.Numeric(15, 2), default=0)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lines = db.relationship("PayrollLine", backref="run", cascade="all, delete-orphan")
    company = db.relationship("Company")

    __table_args__ = (
        db.UniqueConstraint("company_id", "period_year", "period_month", name="uq_payroll_period"),
    )


class PayrollLine(db.Model):
    __tablename__ = "payroll_lines"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    basic = db.Column(db.Numeric(15, 2), default=0)
    allowances = db.Column(db.Numeric(15, 2), default=0)
    overtime = db.Column(db.Numeric(15, 2), default=0)
    deductions = db.Column(db.Numeric(15, 2), default=0)
    net = db.Column(db.Numeric(15, 2), default=0)

    employee = db.relationship("Employee")

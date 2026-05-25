import enum
from datetime import datetime, date
from app import db


class ContractType(enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    TEMPORARY = "TEMPORARY"


class EmployeeStatus(enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class TerminationReason(enum.Enum):
    RESIGNATION = "RESIGNATION"
    DISMISSAL = "DISMISSAL"
    CONTRACT_END = "CONTRACT_END"
    OTHER = "OTHER"


class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    employee_number = db.Column(db.String(20), index=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    job_title = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    contract_type = db.Column(db.Enum(ContractType), default=ContractType.FULL_TIME)
    status = db.Column(db.Enum(EmployeeStatus), default=EmployeeStatus.ACTIVE, index=True)

    basic_salary = db.Column(db.Numeric(15, 2), default=0)
    allowances = db.Column(db.Numeric(15, 2), default=0)
    deductions = db.Column(db.Numeric(15, 2), default=0)

    termination_date = db.Column(db.Date)
    termination_reason = db.Column(db.Enum(TerminationReason))
    termination_notes = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True)  # legacy mirror — kept in sync with status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company", backref=db.backref("employees", lazy="dynamic"))

    @property
    def total_received(self):
        """Sum of all net payments across past payroll runs."""
        return sum(float(l.net or 0) for l in self.payroll_lines)

    @property
    def last_payslip(self):
        return PayrollLine.query.filter_by(employee_id=self.id).join(PayrollRun).order_by(
            PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
        ).first()


class PayrollRun(db.Model):
    __tablename__ = "payroll_runs"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    number = db.Column(db.String(20), index=True)
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
    """One employee's line in a monthly payroll run.

    All variable fields (overtime, bonus, absence/late/advance deductions) live
    here, not on Employee — they reset each month because each run gets a fresh
    set of lines.
    """
    __tablename__ = "payroll_lines"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)

    working_days = db.Column(db.Integer, default=30)
    basic = db.Column(db.Numeric(15, 2), default=0)        # prorated (basic / 30 × working_days)
    allowances = db.Column(db.Numeric(15, 2), default=0)
    overtime = db.Column(db.Numeric(15, 2), default=0)
    bonus = db.Column(db.Numeric(15, 2), default=0)
    deductions = db.Column(db.Numeric(15, 2), default=0)   # fixed deductions from employee
    absence_deduction = db.Column(db.Numeric(15, 2), default=0)
    late_deduction = db.Column(db.Numeric(15, 2), default=0)
    advance_deduction = db.Column(db.Numeric(15, 2), default=0)

    net = db.Column(db.Numeric(15, 2), default=0)

    employee = db.relationship("Employee", backref="payroll_lines")

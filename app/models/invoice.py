import enum
from datetime import datetime, date
from app import db


class InvoiceStatus(enum.Enum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    number = db.Column(db.String(20), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    issue_date = db.Column(db.Date, default=date.today, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    currency = db.Column(db.String(3), default="SAR")
    subtotal = db.Column(db.Numeric(15, 4), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=15.00)
    tax_amount = db.Column(db.Numeric(15, 4), default=0)
    total = db.Column(db.Numeric(15, 4), default=0)
    paid_amount = db.Column(db.Numeric(15, 4), default=0)
    status = db.Column(db.Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company", backref=db.backref("invoices", lazy="dynamic"))
    customer = db.relationship("Customer", backref=db.backref("invoices", lazy="dynamic"))
    items = db.relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="invoice", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("company_id", "number", name="uq_company_invoice_number"),
    )

    @property
    def balance(self):
        return float(self.total or 0) - float(self.paid_amount or 0)

    def recalc(self):
        self.subtotal = sum(float(i.quantity) * float(i.unit_price) for i in self.items)
        self.tax_amount = float(self.subtotal) * float(self.tax_rate or 0) / 100.0
        self.total = float(self.subtotal) + float(self.tax_amount)


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1)
    unit_price = db.Column(db.Numeric(15, 4), default=0)

    @property
    def total(self):
        return float(self.quantity) * float(self.unit_price)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    amount = db.Column(db.Numeric(15, 4), nullable=False)
    payment_date = db.Column(db.Date, default=date.today, nullable=False)
    method = db.Column(db.String(30), default="cash")
    notes = db.Column(db.Text)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

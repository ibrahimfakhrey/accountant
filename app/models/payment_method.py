from app import db


class PaymentMethod(db.Model):
    """A configurable way to receive payments, each linked to a Chart of Accounts line.

    Default methods (cash → 1110, bank → 1120) are seeded with each company.
    Owners can add Visa, STC Pay, MADA, cheques, etc., and link each to its own
    account so the ledger reflects which channel the money landed in.
    """
    __tablename__ = "payment_methods"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    name = db.Column(db.String(50), nullable=False)
    name_ar = db.Column(db.String(50))
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)

    company = db.relationship("Company", backref=db.backref("payment_methods", lazy="dynamic"))
    account = db.relationship("Account")

    __table_args__ = (
        db.UniqueConstraint("company_id", "name", name="uq_pm_company_name"),
    )

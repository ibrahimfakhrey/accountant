import enum
from app import db


class AccountType(enum.Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class NormalSide(enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


NORMAL_SIDE_FOR_TYPE = {
    AccountType.ASSET: NormalSide.DEBIT,
    AccountType.EXPENSE: NormalSide.DEBIT,
    AccountType.LIABILITY: NormalSide.CREDIT,
    AccountType.EQUITY: NormalSide.CREDIT,
    AccountType.REVENUE: NormalSide.CREDIT,
}


class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    name_ar = db.Column(db.String(150))
    type = db.Column(db.Enum(AccountType), nullable=False)
    normal_side = db.Column(db.Enum(NormalSide), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    is_active = db.Column(db.Boolean, default=True)

    company = db.relationship("Company", backref=db.backref("accounts", lazy="dynamic"))
    children = db.relationship(
        "Account",
        backref=db.backref("parent", remote_side=[id]),
        lazy="select",
    )

    __table_args__ = (
        db.UniqueConstraint("company_id", "code", name="uq_company_account_code"),
    )

    @property
    def balance(self):
        """Net balance, excluding paused journal entries."""
        from app.models.journal import JournalLine, JournalEntry
        from sqlalchemy import func
        result = db.session.query(
            func.coalesce(func.sum(JournalLine.debit_base), 0),
            func.coalesce(func.sum(JournalLine.credit_base), 0),
        ).select_from(JournalLine).join(JournalEntry).filter(
            JournalLine.account_id == self.id,
            JournalEntry.is_active.is_(True),
        ).first()
        debit, credit = float(result[0] or 0), float(result[1] or 0)
        if self.normal_side == NormalSide.DEBIT:
            return debit - credit
        return credit - debit

    def __repr__(self):
        return f"<Account {self.code} {self.name}>"

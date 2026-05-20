from datetime import datetime, date
from app import db


class FixedAsset(db.Model):
    __tablename__ = "fixed_assets"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    purchase_date = db.Column(db.Date, default=date.today, nullable=False)
    cost = db.Column(db.Numeric(15, 4), nullable=False)
    salvage_value = db.Column(db.Numeric(15, 4), default=0)
    useful_life_years = db.Column(db.Integer, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    accumulated_depreciation = db.Column(db.Numeric(15, 4), default=0)
    is_disposed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company", backref=db.backref("assets", lazy="dynamic"))
    account = db.relationship("Account")

    @property
    def annual_depreciation(self):
        return (float(self.cost) - float(self.salvage_value)) / max(self.useful_life_years, 1)

    @property
    def monthly_depreciation(self):
        return self.annual_depreciation / 12.0

    @property
    def net_book_value(self):
        return float(self.cost) - float(self.accumulated_depreciation or 0)

from datetime import datetime
from app import db


class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    base_currency = db.Column(db.String(3), default="SAR", nullable=False)
    logo_url = db.Column(db.Text)
    address = db.Column(db.Text)
    tax_number = db.Column(db.String(50))
    vat_rate = db.Column(db.Numeric(5, 2), default=15.00)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Company {self.name}>"

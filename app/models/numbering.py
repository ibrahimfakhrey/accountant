from app import db


class NumberSequence(db.Model):
    """Per-company sequential counter for each document type.

    Each row owns the next number to assign for a (company_id, doc_type) pair.
    Counters are independent across companies — Company A's INV-0001 and
    Company B's INV-0001 coexist.
    """
    __tablename__ = "number_sequences"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    doc_type = db.Column(db.String(20), nullable=False)
    next_number = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint("company_id", "doc_type", name="uq_sequence_company_type"),
    )

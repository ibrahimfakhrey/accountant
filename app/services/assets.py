"""Fixed asset depreciation posting."""
from app import db
from app.models import FixedAsset
from app.services.ledger import post_journal, get_account_by_code, LedgerError


def post_monthly_depreciation(company_id, year, month, created_by=None):
    assets = FixedAsset.query.filter_by(company_id=company_id, is_disposed=False).all()
    if not assets:
        return None

    dep_expense = get_account_by_code(company_id, "5250")
    accumulated = get_account_by_code(company_id, "1290")
    if not dep_expense or not accumulated:
        raise LedgerError("حسابات الاستهلاك غير موجودة")

    total = 0.0
    for asset in assets:
        monthly = asset.monthly_depreciation
        if monthly <= 0:
            continue
        if float(asset.accumulated_depreciation or 0) + monthly > float(asset.cost) - float(asset.salvage_value):
            continue
        asset.accumulated_depreciation = float(asset.accumulated_depreciation or 0) + monthly
        total += monthly

    if total <= 0:
        return None

    entry = post_journal(
        company_id=company_id,
        description=f"استهلاك شهر {month}/{year}",
        lines=[
            {"account_id": dep_expense.id, "debit": total, "credit": 0},
            {"account_id": accumulated.id, "debit": 0, "credit": total},
        ],
        reference=f"DEPR-{year}-{month:02d}",
        created_by=created_by,
        source_type="depreciation",
    )
    return entry

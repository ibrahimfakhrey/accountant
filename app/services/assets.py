"""Fixed asset depreciation posting."""
from app import db
from app.models import FixedAsset
from app.services.ledger import post_journal, get_account_by_code, LedgerError


# Funding source code → CoA account code lookup
FUNDING_ACCOUNT_CODES = {
    "cash": "1110",
    "bank": "1120",
    "credit": "2110",  # Accounts Payable
}


def post_asset_purchase(asset, funding="cash", created_by=None):
    """Dr Fixed Asset / Cr Cash (or Bank, or Accounts Payable).

    Called once when a new asset is recorded. Without this, the asset module
    only tracks depreciation and the asset cost never lands on the ledger.
    """
    if float(asset.cost or 0) <= 0:
        return None
    source_code = FUNDING_ACCOUNT_CODES.get(funding, "1110")
    source = get_account_by_code(asset.company_id, source_code)
    if not source:
        raise LedgerError(f"حساب التمويل ({source_code}) غير موجود")

    return post_journal(
        company_id=asset.company_id,
        description=f"شراء أصل ثابت: {asset.name}",
        lines=[
            {"account_id": asset.account_id, "debit": float(asset.cost), "credit": 0, "memo": "تكلفة الأصل"},
            {"account_id": source.id, "debit": 0, "credit": float(asset.cost), "memo": "تمويل الشراء"},
        ],
        entry_date=asset.purchase_date,
        reference=f"ASSET-{asset.id}",
        created_by=created_by,
        source_type="asset_purchase",
        source_id=asset.id,
    )


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

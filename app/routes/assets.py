from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required, current_user
from app import db
from app.models import FixedAsset, Account
from app.services.assets import post_monthly_depreciation, post_asset_purchase
from app.services.ledger import LedgerError

bp = Blueprint("assets", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    assets = FixedAsset.query.filter_by(company_id=g.active_company.id).order_by(FixedAsset.created_at.desc()).all()
    return render_template("assets/index.html", assets=assets)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    fixed_accounts = Account.query.filter(
        Account.company_id == g.active_company.id,
        Account.code.like("12%"),
    ).all()
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            purchase_date = datetime.strptime(request.form.get("purchase_date", date.today().isoformat()), "%Y-%m-%d").date()
            cost = float(request.form.get("cost", 0))
            salvage = float(request.form.get("salvage_value", 0))
            life = int(request.form.get("useful_life_years", 1))
            account_id = int(request.form.get("account_id"))
            funding = request.form.get("funding", "cash")
            if life <= 0:
                raise ValueError("العمر الإنتاجي يجب أن يكون أكبر من صفر")
            asset = FixedAsset(
                company_id=g.active_company.id,
                name=name,
                purchase_date=purchase_date,
                cost=cost,
                salvage_value=salvage,
                useful_life_years=life,
                account_id=account_id,
            )
            db.session.add(asset)
            db.session.flush()
            post_asset_purchase(asset, funding=funding, created_by=current_user.id)
            db.session.commit()
            flash("تم تسجيل الأصل وقيد الشراء", "success")
            return redirect(url_for("assets.index"))
        except (ValueError, KeyError, LedgerError) as e:
            db.session.rollback()
            flash(str(e), "error")
    return render_template("assets/form.html", fixed_accounts=fixed_accounts)


@bp.route("/depreciate", methods=["POST"])
@login_required
def depreciate():
    today = date.today()
    try:
        entry = post_monthly_depreciation(g.active_company.id, today.year, today.month, created_by=current_user.id)
        if entry:
            flash("تم تسجيل قيد الاستهلاك الشهري", "success")
        else:
            flash("لا يوجد استهلاك للتسجيل", "info")
    except LedgerError as e:
        flash(str(e), "error")
    return redirect(url_for("assets.index"))

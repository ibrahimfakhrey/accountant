from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required
from app import db
from app.models import Account, AccountType, NormalSide
from app.models.account import NORMAL_SIDE_FOR_TYPE

bp = Blueprint("accounts", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    accounts = Account.query.filter_by(company_id=g.active_company.id).order_by(Account.code).all()
    # build tree
    by_id = {a.id: a for a in accounts}
    tree = []
    children_map = {}
    for a in accounts:
        children_map.setdefault(a.parent_id, []).append(a)
    roots = children_map.get(None, [])
    return render_template("accounts/index.html", accounts=accounts, roots=roots, children_map=children_map)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    parents = Account.query.filter_by(company_id=g.active_company.id).order_by(Account.code).all()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        name_ar = request.form.get("name_ar", "").strip()
        type_str = request.form.get("type")
        parent_id = request.form.get("parent_id") or None
        if parent_id == "":
            parent_id = None
        try:
            acc_type = AccountType[type_str]
        except KeyError:
            flash("نوع الحساب غير صحيح", "error")
            return render_template("accounts/form.html", parents=parents)
        if Account.query.filter_by(company_id=g.active_company.id, code=code).first():
            flash("الكود مستخدم بالفعل", "error")
            return render_template("accounts/form.html", parents=parents)
        acc = Account(
            company_id=g.active_company.id,
            code=code,
            name=name,
            name_ar=name_ar,
            type=acc_type,
            normal_side=NORMAL_SIDE_FOR_TYPE[acc_type],
            parent_id=int(parent_id) if parent_id else None,
        )
        db.session.add(acc)
        db.session.commit()
        flash("تم إضافة الحساب", "success")
        return redirect(url_for("accounts.index"))
    return render_template("accounts/form.html", parents=parents, account_types=AccountType)


@bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
def delete(account_id):
    acc = db.session.get(Account, account_id)
    if not acc or acc.company_id != g.active_company.id:
        flash("غير مسموح", "error")
        return redirect(url_for("accounts.index"))
    if acc.lines.count() > 0:
        flash("لا يمكن حذف حساب له قيود — تم تعطيله بدلاً من ذلك", "warning")
        acc.is_active = False
        db.session.commit()
    else:
        db.session.delete(acc)
        db.session.commit()
        flash("تم الحذف", "success")
    return redirect(url_for("accounts.index"))

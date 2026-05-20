from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from flask_login import login_required
from app import db
from app.models import Vendor

bp = Blueprint("vendors", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    vendors = Vendor.query.filter_by(company_id=g.active_company.id).order_by(Vendor.name).all()
    return render_template("vendors/index.html", vendors=vendors)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        v = Vendor(
            company_id=g.active_company.id,
            name=request.form.get("name", "").strip(),
            email=request.form.get("email", "").strip(),
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip(),
            bank_account=request.form.get("bank_account", "").strip(),
            tax_number=request.form.get("tax_number", "").strip(),
        )
        if not v.name:
            flash("الاسم مطلوب", "error")
            return render_template("vendors/form.html")
        db.session.add(v)
        db.session.commit()
        flash("تم إضافة المورد", "success")
        return redirect(url_for("vendors.index"))
    return render_template("vendors/form.html")

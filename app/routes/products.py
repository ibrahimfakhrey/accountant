from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, g
from flask_login import login_required
from app import db
from app.models import Product
from app.services.permissions import require_permission

bp = Blueprint("products", __name__)


@bp.route("/")
@login_required
def index():
    if not g.active_company:
        return redirect(url_for("companies.new"))
    products = Product.query.filter_by(company_id=g.active_company.id).order_by(Product.name).all()
    return render_template("products/index.html", products=products)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@require_permission("products.manage")
def new():
    if request.method == "POST":
        try:
            p = Product(
                company_id=g.active_company.id,
                name=request.form.get("name", "").strip(),
                description=request.form.get("description", "").strip(),
                default_price=float(request.form.get("default_price", 0)),
                default_tax_rate=float(request.form.get("default_tax_rate") or 0) or None,
                sku=request.form.get("sku", "").strip(),
            )
            if not p.name:
                raise ValueError("الاسم مطلوب")
            db.session.add(p)
            db.session.commit()
            flash("تم إضافة المنتج/الخدمة", "success")
            return redirect(url_for("products.index"))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("products/form.html")


@bp.route("/api/list")
@login_required
def api_list():
    """JSON endpoint for invoice form autocomplete."""
    products = Product.query.filter_by(
        company_id=g.active_company.id, is_active=True
    ).order_by(Product.name).all()
    return jsonify([
        {
            "id": p.id, "name": p.name, "description": p.description or "",
            "price": float(p.default_price or 0),
            "tax_rate": float(p.default_tax_rate) if p.default_tax_rate is not None else None,
        } for p in products
    ])

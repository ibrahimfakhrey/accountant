from flask import Blueprint, render_template, redirect, url_for, flash, request, session, g
from flask_login import login_required, current_user
from app import db
from app.models import Company
from app.models.user import user_companies
from app.services.seed_coa import seed_default_coa
from app.services.permissions import require_permission

bp = Blueprint("companies", __name__)


@bp.route("/")
@login_required
def index():
    return render_template("companies/index.html", companies=current_user.companies)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        base_currency = request.form.get("base_currency", "SAR")
        tax_number = request.form.get("tax_number", "").strip()
        vat_rate = float(request.form.get("vat_rate", 15))
        address = request.form.get("address", "").strip()
        if not name:
            flash("اسم الشركة مطلوب", "error")
            return render_template("companies/form.html")
        if any(c.name == name for c in current_user.companies):
            flash("يوجد شركة بنفس الاسم", "error")
            return render_template("companies/form.html")

        company = Company(
            name=name,
            base_currency=base_currency,
            tax_number=tax_number,
            vat_rate=vat_rate,
            address=address,
        )
        db.session.add(company)
        db.session.flush()
        db.session.execute(user_companies.insert().values(
            user_id=current_user.id, company_id=company.id, role="owner",
        ))
        db.session.commit()
        seed_default_coa(company.id)
        session["active_company_id"] = company.id
        flash("تم إنشاء الشركة وشجرة الحسابات الافتراضية", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("companies/form.html")


@bp.route("/<int:company_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("company.edit")
def edit(company_id):
    company = db.session.get(Company, company_id)
    if not company or company not in current_user.companies:
        flash("غير مسموح", "error")
        return redirect(url_for("companies.index"))
    if request.method == "POST":
        company.name = request.form.get("name", company.name).strip()
        company.tax_number = request.form.get("tax_number", company.tax_number)
        company.vat_rate = float(request.form.get("vat_rate", company.vat_rate))
        company.address = request.form.get("address", company.address)

        # Reminder config (T13) — parse comma-separated day lists.
        def _parse_days(s):
            out = []
            for piece in (s or "").split(","):
                piece = piece.strip()
                if not piece:
                    continue
                try:
                    n = int(piece)
                    if n >= 0:
                        out.append(n)
                except ValueError:
                    pass
            return sorted(set(out), reverse=True)
        company.set_reminders({
            "enabled": request.form.get("reminders_enabled") == "1",
            "days_before": _parse_days(request.form.get("reminders_days_before", "7,3")),
            "overdue_days": _parse_days(request.form.get("reminders_overdue_days", "0")),
        })

        db.session.commit()
        flash("تم الحفظ", "success")
        return redirect(url_for("companies.index"))
    return render_template("companies/form.html", company=company)

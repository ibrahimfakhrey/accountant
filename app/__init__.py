from flask import Flask, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    migrate.init_app(app, db)

    from app.models import User, Company

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.companies import bp as companies_bp
    from app.routes.accounts import bp as accounts_bp
    from app.routes.journals import bp as journals_bp
    from app.routes.invoices import bp as invoices_bp
    from app.routes.customers import bp as customers_bp
    from app.routes.vendors import bp as vendors_bp
    from app.routes.assets import bp as assets_bp
    from app.routes.payroll import bp as payroll_bp
    from app.routes.reports import bp as reports_bp
    from app.routes.agent import bp as agent_bp
    from app.routes.cron import bp as cron_bp
    from app.routes.products import bp as products_bp
    from app.routes.payment_methods import bp as pmethods_bp
    from app.routes.vendor_bills import bp as vbills_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp, url_prefix="/companies")
    app.register_blueprint(accounts_bp, url_prefix="/accounts")
    app.register_blueprint(journals_bp, url_prefix="/journals")
    app.register_blueprint(invoices_bp, url_prefix="/invoices")
    app.register_blueprint(customers_bp, url_prefix="/customers")
    app.register_blueprint(vendors_bp, url_prefix="/vendors")
    app.register_blueprint(assets_bp, url_prefix="/assets")
    app.register_blueprint(payroll_bp, url_prefix="/payroll")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(agent_bp, url_prefix="/agent")
    app.register_blueprint(cron_bp, url_prefix="/cron")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(pmethods_bp, url_prefix="/payment-methods")
    app.register_blueprint(vbills_bp, url_prefix="/vendor-bills")

    @app.before_request
    def load_active_company():
        from flask_login import current_user
        g.active_company = None
        g.user_companies = []
        if current_user.is_authenticated:
            g.user_companies = current_user.companies
            cid = session.get("active_company_id")
            if cid:
                comp = db.session.get(Company, cid)
                if comp and comp in current_user.companies:
                    g.active_company = comp
            if not g.active_company and current_user.companies:
                g.active_company = current_user.companies[0]
                session["active_company_id"] = g.active_company.id

    @app.context_processor
    def inject_globals():
        return {
            "active_company": g.get("active_company"),
            "user_companies": g.get("user_companies", []),
        }

    @app.template_filter("money")
    def money_filter(value, currency=None):
        if value is None:
            return "0.00"
        try:
            return f"{float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

    return app

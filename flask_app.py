from app import create_app, db
from app.models import User, Company, Account, JournalEntry, JournalLine, Invoice, Customer, Vendor

app = create_app()


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db,
        "User": User,
        "Company": Company,
        "Account": Account,
        "JournalEntry": JournalEntry,
        "JournalLine": JournalLine,
        "Invoice": Invoice,
        "Customer": Customer,
        "Vendor": Vendor,
    }


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)

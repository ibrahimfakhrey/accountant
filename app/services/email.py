"""Email service with SMTP + log-only fallback.

If SMTP_HOST is not configured, emails are logged to console instead of sent —
this keeps dev environments functional without requiring credentials.
"""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
from flask import current_app, render_template

logger = logging.getLogger("ledgeros.email")


def _smtp_configured():
    return bool(current_app.config.get("SMTP_HOST"))


def send_email(to, subject, html_body, attachments=None, text_body=None):
    """Send an email. Returns True on success, False on failure (logged, never raises).

    attachments: list of (filename, bytes, mimetype) tuples
    """
    if not to:
        logger.warning("send_email called with empty 'to'")
        return False

    config = current_app.config
    from_addr = config.get("SMTP_FROM", "no-reply@marsoud.app")
    from_name = config.get("SMTP_FROM_NAME", "Marsoud")

    if not _smtp_configured():
        # Log-only mode for dev
        logger.info(
            "[EMAIL — log only, SMTP not configured]\n"
            "  To:      %s\n"
            "  Subject: %s\n"
            "  Body:    %s\n"
            "  Attachments: %s",
            to, subject, (text_body or html_body)[:200],
            [a[0] for a in (attachments or [])],
        )
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = to

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if attachments:
        mixed = MIMEMultipart("mixed")
        mixed.attach(msg)
        for filename, data, mimetype in attachments:
            main, sub = (mimetype.split("/", 1) + ["octet-stream"])[:2]
            part = MIMEApplication(data, _subtype=sub)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            mixed.attach(part)
        mixed["Subject"] = subject
        mixed["From"] = formataddr((from_name, from_addr))
        mixed["To"] = to
        msg = mixed

    try:
        with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"]) as server:
            if config.get("SMTP_USE_TLS", True):
                server.starttls()
            if config.get("SMTP_USER"):
                server.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            server.send_message(msg)
        logger.info("Email sent → %s (subject=%r)", to, subject)
        return True
    except Exception as e:
        logger.exception("SMTP send failed: %s", e)
        return False


def send_invoice_email(invoice, attach_pdf=True):
    """Notify customer of a sent invoice. Attaches PDF if requested."""
    if not invoice.customer.email:
        logger.info("Skip invoice email: customer %s has no email", invoice.customer.name)
        return False
    subject = f"فاتورة جديدة #{invoice.number} من {invoice.company.name}"
    html = render_template("emails/invoice_sent.html", invoice=invoice)
    attachments = []
    if attach_pdf:
        try:
            from app.services.export import export_invoice_pdf
            pdf = export_invoice_pdf(invoice)
            attachments.append((f"invoice-{invoice.number}.pdf", pdf.getvalue(), "application/pdf"))
        except Exception as e:
            logger.warning("Could not attach invoice PDF: %s", e)
    return send_email(invoice.customer.email, subject, html, attachments=attachments)


def send_payment_received_email(invoice, payment, is_full):
    if not invoice.customer.email:
        return False
    template = "emails/payment_full.html" if is_full else "emails/payment_partial.html"
    label = "تم سداد فاتورة" if is_full else "تم تسجيل دفعة جزئية"
    subject = f"{label} #{invoice.number}"
    html = render_template(template, invoice=invoice, payment=payment)
    return send_email(invoice.customer.email, subject, html)


def send_overdue_reminder(invoice, days_label):
    """days_label: 'before_7', 'before_3', or 'overdue'"""
    if not invoice.customer.email:
        return False
    if days_label == "before_7":
        subject = f"تذكير: فاتورة #{invoice.number} تستحق خلال 7 أيام"
    elif days_label == "before_3":
        subject = f"تذكير: فاتورة #{invoice.number} تستحق خلال 3 أيام"
    else:
        subject = f"فاتورة #{invoice.number} تجاوزت تاريخ الاستحقاق"
    html = render_template("emails/invoice_reminder.html", invoice=invoice, days_label=days_label)
    return send_email(invoice.customer.email, subject, html)


def send_payslip_email(employee, payroll_line, payroll_run, pdf_bytes=None):
    if not employee.email:
        return False
    subject = f"كشف راتب {payroll_run.period_month}/{payroll_run.period_year} — {employee.name}"
    html = render_template("emails/payslip.html", employee=employee, line=payroll_line, run=payroll_run)
    attachments = []
    if pdf_bytes:
        attachments.append((f"payslip-{payroll_run.period_year}-{payroll_run.period_month:02d}.pdf", pdf_bytes, "application/pdf"))
    return send_email(employee.email, subject, html, attachments=attachments)

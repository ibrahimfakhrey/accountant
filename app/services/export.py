"""PDF and Excel export for financial reports."""
import io
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from app.services.reports import balance_sheet, income_statement, cash_flow

NAVY = colors.HexColor("#0A2540")
BLUE = colors.HexColor("#2563EB")
GRAY = colors.HexColor("#64748B")


def _excel_styled_header(ws, title, company_name, period):
    ws["A1"] = company_name
    ws["A1"].font = Font(size=16, bold=True, color="0A2540")
    ws["A2"] = title
    ws["A2"].font = Font(size=14, bold=True, color="2563EB")
    ws["A3"] = period
    ws["A3"].font = Font(size=10, color="64748B")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 18


def export_balance_sheet_excel(company, as_of):
    data = balance_sheet(company.id, as_of=as_of)
    wb = Workbook()
    ws = wb.active
    ws.title = "Balance Sheet"
    _excel_styled_header(ws, "Balance Sheet — الميزانية العمومية", company.name, f"كما في {as_of}")

    row = 5
    ws.cell(row=row, column=1, value="الأصول").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="0A2540")
    row += 1
    for item in data["assets"]:
        ws.cell(row=row, column=1, value=f"  {item['code']} — {item['name']}")
        ws.cell(row=row, column=2, value=item["balance"]).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=1, value="إجمالي الأصول").font = Font(bold=True)
    ws.cell(row=row, column=2, value=data["totals"]["assets"]).font = Font(bold=True)
    ws.cell(row=row, column=2).number_format = "#,##0.00"
    row += 2

    ws.cell(row=row, column=1, value="الالتزامات").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="0A2540")
    row += 1
    for item in data["liabilities"]:
        ws.cell(row=row, column=1, value=f"  {item['code']} — {item['name']}")
        ws.cell(row=row, column=2, value=item["balance"]).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=1, value="إجمالي الالتزامات").font = Font(bold=True)
    ws.cell(row=row, column=2, value=data["totals"]["liabilities"]).font = Font(bold=True)
    row += 2

    ws.cell(row=row, column=1, value="حقوق الملكية").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="0A2540")
    row += 1
    for item in data["equity"]:
        ws.cell(row=row, column=1, value=f"  {item['code']} — {item['name']}")
        ws.cell(row=row, column=2, value=item["balance"]).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=1, value="إجمالي حقوق الملكية").font = Font(bold=True)
    ws.cell(row=row, column=2, value=data["totals"]["equity"]).font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_income_statement_excel(company, start, end):
    data = income_statement(company.id, start_date=start, end_date=end)
    wb = Workbook()
    ws = wb.active
    ws.title = "Income Statement"
    _excel_styled_header(ws, "Income Statement — قائمة الدخل", company.name, f"من {start} إلى {end}")

    row = 5
    ws.cell(row=row, column=1, value="الإيرادات").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="0A2540")
    row += 1
    for item in data["revenue"]:
        ws.cell(row=row, column=1, value=f"  {item['code']} — {item['name']}")
        ws.cell(row=row, column=2, value=item["balance"]).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=1, value="إجمالي الإيرادات").font = Font(bold=True)
    ws.cell(row=row, column=2, value=data["total_revenue"]).font = Font(bold=True)
    row += 2

    ws.cell(row=row, column=1, value="المصروفات").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor="0A2540")
    row += 1
    for item in data["expenses"]:
        ws.cell(row=row, column=1, value=f"  {item['code']} — {item['name']}")
        ws.cell(row=row, column=2, value=item["balance"]).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=1, value="إجمالي المصروفات").font = Font(bold=True)
    ws.cell(row=row, column=2, value=data["total_expense"]).font = Font(bold=True)
    row += 2

    color = "10B981" if data["net_income"] >= 0 else "EF4444"
    ws.cell(row=row, column=1, value="صافي الربح / الخسارة").font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=1).fill = PatternFill("solid", fgColor=color)
    ws.cell(row=row, column=2, value=data["net_income"]).font = Font(bold=True, color="FFFFFF")
    ws.cell(row=row, column=2).fill = PatternFill("solid", fgColor=color)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _pdf_header(p, company, title, period):
    p.setFillColor(NAVY)
    p.rect(0, 27.7 * cm, 21 * cm, 2 * cm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 18)
    p.drawString(1.5 * cm, 28.5 * cm, company.name)
    p.setFont("Helvetica", 10)
    p.drawString(1.5 * cm, 28 * cm, "LedgerOS Financial Report")

    p.setFillColor(NAVY)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(1.5 * cm, 26.5 * cm, title)
    p.setFillColor(GRAY)
    p.setFont("Helvetica", 10)
    p.drawString(1.5 * cm, 26 * cm, period)


def _pdf_section(p, y, label):
    p.setFillColor(NAVY)
    p.rect(1 * cm, y - 0.4 * cm, 19 * cm, 0.7 * cm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(1.3 * cm, y - 0.2 * cm, label)
    return y - 1 * cm


def export_balance_sheet_pdf(company, as_of):
    data = balance_sheet(company.id, as_of=as_of)
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    _pdf_header(p, company, "Balance Sheet", f"As of {as_of}")

    y = 24.5 * cm
    for section, items, total_key in [
        ("ASSETS", data["assets"], "assets"),
        ("LIABILITIES", data["liabilities"], "liabilities"),
        ("EQUITY", data["equity"], "equity"),
    ]:
        y = _pdf_section(p, y, section)
        p.setFillColor(colors.black)
        p.setFont("Helvetica", 10)
        for item in items:
            if y < 3 * cm:
                p.showPage()
                _pdf_header(p, company, "Balance Sheet (cont.)", f"As of {as_of}")
                y = 24.5 * cm
            p.drawString(1.5 * cm, y, f"{item['code']}  {item['name']}")
            p.drawRightString(19.5 * cm, y, f"{item['balance']:,.2f}")
            y -= 0.5 * cm
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(BLUE)
        p.drawString(1.5 * cm, y, f"Total {section}")
        p.drawRightString(19.5 * cm, y, f"{data['totals'][total_key]:,.2f}")
        p.setFillColor(colors.black)
        y -= 1 * cm

    p.showPage()
    p.save()
    buf.seek(0)
    return buf


def export_income_statement_pdf(company, start, end):
    data = income_statement(company.id, start_date=start, end_date=end)
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=A4)
    _pdf_header(p, company, "Income Statement", f"{start} → {end}")

    y = 24.5 * cm
    for section, items, total_key in [
        ("REVENUE", data["revenue"], "total_revenue"),
        ("EXPENSES", data["expenses"], "total_expense"),
    ]:
        y = _pdf_section(p, y, section)
        p.setFillColor(colors.black)
        p.setFont("Helvetica", 10)
        for item in items:
            p.drawString(1.5 * cm, y, f"{item['code']}  {item['name']}")
            p.drawRightString(19.5 * cm, y, f"{item['balance']:,.2f}")
            y -= 0.5 * cm
        p.setFont("Helvetica-Bold", 10)
        p.setFillColor(BLUE)
        p.drawString(1.5 * cm, y, f"Total {section}")
        p.drawRightString(19.5 * cm, y, f"{data[total_key]:,.2f}")
        p.setFillColor(colors.black)
        y -= 1 * cm

    y -= 0.3 * cm
    profit = data["net_income"]
    color = colors.HexColor("#10B981") if profit >= 0 else colors.HexColor("#EF4444")
    p.setFillColor(color)
    p.rect(1 * cm, y - 0.5 * cm, 19 * cm, 0.9 * cm, fill=1, stroke=0)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 13)
    p.drawString(1.5 * cm, y - 0.2 * cm, "NET PROFIT / (LOSS)")
    p.drawRightString(19.5 * cm, y - 0.2 * cm, f"{profit:,.2f}")

    p.showPage()
    p.save()
    buf.seek(0)
    return buf


def export_report(company, report_type, fmt, start, end):
    if report_type == "balance-sheet":
        if fmt == "pdf":
            return export_balance_sheet_pdf(company, end), f"balance-sheet-{end}.pdf", "application/pdf"
        return export_balance_sheet_excel(company, end), f"balance-sheet-{end}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif report_type == "income-statement":
        if fmt == "pdf":
            return export_income_statement_pdf(company, start, end), f"income-statement-{start}-{end}.pdf", "application/pdf"
        return export_income_statement_excel(company, start, end), f"income-statement-{start}-{end}.xlsx", \
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    raise ValueError(f"Unknown report: {report_type}")

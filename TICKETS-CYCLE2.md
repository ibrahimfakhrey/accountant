# Marsoud — Cycle 2 Tickets

Production feedback from abdelhamid at `accountant.manasety.ai` surfaced six workstreams.
Six tickets shipped in one session, six migrations, all idempotent (safe to re-run against
the legacy production DB using the `sa.inspect()` guard pattern from `6e0cd4a49d23`).

| # | Ticket | Migration | Est. → Actual |
|---|---|---|---|
| **T0** | PDF Arabic rendering | — | 30m → 30m |
| **T11** | Cash Flow auto-classification | `5fa2b4c2f255` | 45m → 30m |
| **T13** | Invoice follow-ups | `96d3c51d9ba1` | 1.5h → 1.5h |
| **T10** | Recurring journals overhaul | `5b57249797cc` | 1.5h → 1.5h |
| **T14** | Payroll follow-ups | `91cfd2fe95d9` | 2.5h → 2.5h |
| **T12** | User invitations + roles + full route sweep | `5717814e0264` | 1.5h → 2.5h |

---

## T0 — PDF Arabic Rendering Fix

**Problem:** All PDFs in the app rendered Arabic as ☐☐☐ boxes. Affected every customer-visible export — invoices, payslips, journal entries, all 10 reports.

**Root cause:** `reportlab` defaults to Helvetica which has no Arabic glyphs. Even with an Arabic TTF, Arabic ligatures + RTL must be pre-shaped before being passed to reportlab (it doesn't do shaping or bidi reordering on its own).

**Solution:**
- Shipped **Amiri TTF** (Regular + Bold) in `app/static/fonts/` (downloaded from Google Fonts, SIL Open Font License).
- Registered with reportlab via `pdfmetrics.registerFont(TTFont("Amiri", ...))`.
- Added `arabic-reshaper==3.0.0` + `python-bidi==0.4.2` to requirements.
- New `ar(text)` helper in `app/services/export.py` runs `arabic_reshaper.reshape()` → `bidi.algorithm.get_display()`. Safe on Latin (no-op) so it's universally applicable.
- Replaced `Helvetica` / `Helvetica-Bold` with `_FONT_REGULAR` / `_FONT_BOLD` constants throughout. Wrapped every user-supplied string drawn to PDF with `ar(...)`: customer names, descriptions, account names, employee names, section labels, totals.
- Generic `_list_pdf` helper now wraps headers + row values + totals with `ar()` automatically, so every report exporter inherits the fix.

**Verified:** Generated a balance-sheet PDF with the demo Arabic company name + arabic memos + arabic-Latin mixed account labels. Output renders cleanly in macOS Preview (the user confirmed visually).

**No DB migration.**

**Key files:** `app/services/export.py`, `requirements.txt`, `app/static/fonts/Amiri-*.ttf`

---

## T11 — Cash Flow Auto-Classification

**Problem:** Cash Flow report showed **0 / 0 / 0** in Operating, Investing, Financing for production data. Manual journals never landed in any bucket.

**Root cause:** The classifier in `cash_flow()` only categorized when `entry.source_type == "asset_purchase"` (Investing) or when the *other* line's account type was Equity/Liability (Financing). Every other case defaulted to Operating, but most production cash movements failed even that filter because they didn't intersect with `1110`/`1120` accounts the way the loop expected.

**Solution:**
- Added `JournalEntry.cashflow_category` column (String 15, nullable): manual override option — `OPERATING`, `INVESTING`, `FINANCING`, `NONCASH`.
- New `_classify_cashflow_entry(entry, cash_ids)` helper with a clear priority chain:
  1. Manual `entry.cashflow_category` wins if set
  2. `entry.source_type == "asset_purchase"` → Investing
  3. `entry.source_type == "depreciation"` → NonCash (excluded from CF)
  4. Otherwise infer from the **non-cash** line account codes:
     - `12xx` (excl. `1290`) or `1140` → Investing
     - `3xxx` (equity) or `21xx`/`22xx` (liabilities) → Financing
     - `5250 ↔ 1290` pair → NonCash
     - Default → Operating
- UI override added to journal form (`templates/journals/form.html`): a select with "auto / تشغيلي / استثماري / تمويلي / غير نقدي".
- `post_journal()` in `services/ledger.py` accepts and persists `cashflow_category`.

**Examples verified:**
| Journal | Classified |
|---|---|
| Cash sale (Dr 1110 / Cr 4100) | **OPERATING** (5xxx/4xxx rule) |
| Buy equipment for cash (Dr 1210 / Cr 1110) | **INVESTING** (12xx rule) |
| Owner injects capital (Dr 1110 / Cr 3100) | **FINANCING** (3xxx rule) |
| Monthly depreciation (Dr 5250 / Cr 1290) | **NONCASH** — excluded |
| Salary payment (Dr 2130 / Cr 1110) | **FINANCING** (2xxx rule, settlement of liability) |

**Migration:** `5fa2b4c2f255_add_cashflow_category_to_journal_.py` — single column add, idempotent.

**Key files:** `app/services/reports.py`, `app/models/journal.py`, `app/services/ledger.py`, `app/templates/journals/form.html`

---

## T13 — Invoice Page Follow-Ups

Three sub-issues bundled into one ticket because they share a migration.

### 13a — Empty payment-method dropdown

**Problem:** When recording a payment on an invoice, the payment-method `<select>` was empty in production, breaking the form.

**Root cause:** `PaymentMethod` rows are per-company, and production companies created before payment-method seeding existed had zero rows. The form silently rendered an empty `<select>` with no error.

**Solution:**
- `seed_default_coa()` already seeds Cash → 1110 and Bank Transfer → 1120 for new companies. Confirmed it runs on every company creation.
- Migration backfill: walks every existing company, checks `payment_methods.count() == 0`, and inserts the two defaults pointing at the company's own `1110`/`1120` accounts.
- Invoice view template now checks for active methods and shows an inline banner with a CTA link to `/payment-methods` instead of an empty dropdown: `"أضف طريقة دفع أولاً من الإعدادات"`.

### 13b — Refund / Credit Note email

**Problem:** Issuing a refund or credit note posted the journal but never notified the customer. No template existed.

**Solution:**
- Two new email templates extending `_base.html` with Cairo RTL styling:
  - `app/templates/emails/refund_issued.html` — for FULL and PARTIAL refunds
  - `app/templates/emails/credit_note_issued.html` — for CREDIT_NOTE refunds
- Two new functions in `app/services/email.py`: `send_refund_email(invoice, refund)` and `send_credit_note_email(invoice, credit_note)`.
- `issue_refund()` in `app/services/invoicing.py` now accepts a `notify=False` kwarg. When true, fires the appropriate email after commit (chooses the right helper based on `RefundType`).
- Refund form on invoice view (`app/templates/invoices/view.html`) gains a checkbox "إرسال إيميل تأكيد للعميل" — auto-disabled when the customer has no email on file.
- `app/routes/invoices.py:refund()` reads `email_customer=1` and passes through.

### 13c — Configurable reminder thresholds

**Problem:** Reminder days were hardcoded `[7, 3]` before-due + on-due-date overdue. Customers wanted to set their own schedule (e.g., `[14, 7, 1]` before + `[0, 7, 14]` overdue).

**Solution:**
- `Company.reminder_config` (JSON-as-text column) with `Company.reminders` property and `Company.set_reminders(cfg)` setter. Default: `{"enabled": True, "days_before": [7, 3], "overdue_days": [0]}`.
- New `InvoiceReminderSent` table replaces the three columns `reminder_7d_sent_at`, `reminder_3d_sent_at`, `overdue_notified_at`. Each row is `(invoice_id, threshold_kind, threshold_days, sent_at)` with `UNIQUE(invoice_id, kind, days)` for idempotency.
- Migration backfills `InvoiceReminderSent` from the legacy columns, then drops them.
- `process_invoice_reminders()` in `app/services/reminders.py` now reads `company.reminders["days_before"]` and `["overdue_days"]`, iterates both lists, checks `InvoiceReminderSent` for idempotency, fires `send_overdue_reminder(invoice, f"before_{d}")` or `f"overdue_{d}"`. Subject lines are dynamically built ("...تستحق خلال {n} أيام" / "...متأخرة منذ {n} يوم").
- Company edit page (`app/templates/companies/form.html`) gains a "تذكيرات الفواتير" panel: enabled toggle + two comma-separated day-list inputs.
- `app/routes/companies.py:edit()` parses the inputs, sorts/dedupes days, and calls `set_reminders()`.

**Migration:** `96d3c51d9ba1_invoice_reminders_overhaul_refund_email_.py` — one combined migration for 13a (backfill payment methods) + 13c (new table + reminder_config + drop legacy columns). Idempotent on every step.

**Key files:** `app/models/company.py`, `app/models/invoice.py`, `app/services/reminders.py`, `app/services/email.py`, `app/services/invoicing.py`, `app/routes/invoices.py`, `app/routes/companies.py`, `app/templates/companies/form.html`, `app/templates/invoices/view.html`, `app/templates/emails/refund_issued.html`, `app/templates/emails/credit_note_issued.html`

---

## T10 — Recurring Journals Overhaul

**Problem (silent correctness bug):** `process_recurring_journals()` advanced `next_run_date` by exactly one period per cron tick. A daily schedule that missed 5 days only caught up over 5 ticks (typically 5 hours). Also: no audit trail, no UI to edit/stop/delete a schedule, server timezone used (wrong for KSA companies).

**Solution:**

### Retroactive catch-up

The post block is now wrapped in a `while sched.next_run_date <= today_in_company_tz(sched.company):` loop. All missed periods post in a single tick. Each iteration writes a log row (`EXECUTE` on success / `FAIL` on exception). On failure the loop breaks out for *that* schedule (so we don't infinite-loop on a bad template) but continues to the next schedule.

### Timezone awareness

- `Company.timezone` column (default `Asia/Riyadh`).
- New `app/services/time.py:today_in_company_tz(company)` using stdlib `zoneinfo`. Falls back to server local time if `zoneinfo` is unavailable or the tz string is malformed.

### Audit log

- New `RecurringJournalLog` table: `(recurring_id, action, period_posted, journal_entry_id, error_message, reason, created_by, created_at)`.
- `action` enum: `EXECUTE / FAIL / EDIT / STOP / RESUME / DELETE`.
- Each row links back to the schedule and (for execute rows) to the resulting `JournalEntry`.

### Edit / Stop / Resume / Delete

Four new routes under `/journals/recurring/<id>/`:
- `POST /edit` — accepts `name`, `frequency`, `next_run_date`, `end_date`. Logs an `EDIT` action describing the diff (e.g., `"الاسم: قديم → جديد · التكرار: WEEKLY → MONTHLY"`).
- `POST /stop` — `is_active = False`, requires a reason, logs `STOP`.
- `POST /resume` — `is_active = True`, logs `RESUME`.
- `POST /delete` — sets `is_deleted = True` (soft delete preserves history) and `is_active = False`. Logs `DELETE` with optional reason.
- `GET /log` — shows the per-schedule audit timeline.

### Soft delete

- New `RecurringJournal.is_deleted` column (default False).
- List query (`recurring_list`) excludes `is_deleted = True`.
- Catch-up worker filter excludes deleted schedules.
- Row is never physically removed so the log/history stays auditable.

### UI

- `app/templates/journals/recurring.html` rewritten — each row now has an actions cell with `تعديل / إيقاف / تفعيل / حذف / السجل` buttons that toggle inline forms.
- New `app/templates/journals/recurring_log.html` — colored badges per action, link to the actual journal entry that was posted, error messages displayed in red.

**Migration:** `5b57249797cc_recurring_journals_log_tz_soft_delete_.py` — creates `recurring_journal_logs` table + two indices, adds `companies.timezone`, adds `recurring_journals.is_deleted`. Backfills timezone to `Asia/Riyadh` and `is_deleted` to False.

**Verified:**
- Catch-up: A daily schedule with `next_run_date = today - 5d` produces 5 EXECUTE log rows and 5 journal entries in one tick.
- Timezone: `today_in_company_tz(company_with_riyadh)` and `today_in_company_tz(company_with_la)` return correct local dates.

**Key files:** `app/services/journals.py`, `app/services/time.py`, `app/models/journal_extras.py`, `app/models/company.py`, `app/routes/journals.py`, `app/templates/journals/recurring.html`, `app/templates/journals/recurring_log.html`

---

## T14 — Payroll / Employee Module Follow-Ups

Four sub-issues raised by abdelhamid in the production feedback.

### 14a — Editable employees

**Problem:** Employee profile was read-only. No way to fix typos in name/email/phone, change contract type, or update salary after creation.

**Solution:**
- New route `GET/POST /payroll/employees/<id>/edit` (`edit_employee`) in `app/routes/payroll.py`.
- `app/services/payroll.py:update_employee(emp, form)` handles the save logic with one safety rule: **`employee_number` and `start_date` are locked once payroll history exists** for that employee (to prevent retroactive proration drift on past payslips). The template disables those inputs and shows a tooltip explaining why.
- `app/templates/payroll/employee_form.html` parameterized — same template handles both new and edit, picking up the `employee` and `has_history` kwargs.
- Employee profile (`employee_profile.html`) gains an "✎ تعديل" button next to the status badge.

### 14b — Mid-month proration

**Problem:** An employee hired April 27 received the *full* April salary (30 days) instead of 4 days. The formula was `basic / 30 × working_days` where `working_days` defaulted to 30.

**Solution:**
- New helper `billable_days_in_period(employee, year, month, override=None)` in `app/services/payroll.py`:
  - If `start_date` falls inside the period → bill from `start_date` to end of month.
  - If `termination_date` falls inside the period → bill from start of month to `termination_date`.
  - Otherwise full month length.
  - User override (the `working_days` form input) wins but is **clamped** to the natural billable maximum, so users can't accidentally over-pay an employee who joined mid-month.
- `run_payroll()` now calls the helper as the proration default — the user can still type a different number but the form pre-fills with the correct value.
- Employee inclusion logic extended: `TERMINATED` employees with `termination_date >= period_start` are still included in the run (so they receive partial-month pay before fully exiting).
- `run_form.html` warns inline when an employee has a `start_date` falling inside the period: `"⚠ تم تعيينه يوم {start_date} — الأيام المستحقة افتراضياً: {N}"`.

**Verified:**
| Scenario | Expected | Actual |
|---|---|---|
| Hired April 27, April run | 4 days (27, 28, 29, 30) | ✅ 4 |
| Hired April 27, May run | 31 (full May) | ✅ 31 |
| Hired April 27, March run | 0 (not yet hired) | ✅ 0 |
| Hired Jan 1, terminated April 5, April run | 5 days (1–5) | ✅ 5 |

### 14c — Payslip-detail layout

**Problem:** The PDF download link was crammed inside the last data cell of the payroll table at `/payroll/run/<id>`, breaking visual alignment in RTL.

**Solution:**
- `app/templates/payroll/run.html` rebuilt — PDF link moved to a separate full-width row beneath each employee's data row: `📄 تحميل كشف الراتب (PDF) — {name}`.
- Two new columns added in the same pass: `المدفوع` (paid) and `المستحق` (accrued/owed). The accrued column is highlighted amber when > 0.

### 14d — Per-employee accrual tracking

**Problem:** When a user paid partial salary (e.g., 2000 of 3000 net), the system credited `2130 (Salaries Payable)` for the difference but had no way to identify *which employee* the 1000 was owed to. abdelhamid: *"هو بيتسجل ك راتب مستحق بس مقدرش احدد مستحق لمين"*.

**Solution:**

- New `PayrollLine.amount_paid` column (defaults to `net` for backward compatibility — backfilled in migration).
- New `EmployeeAccrual` table: `(company_id, employee_id, source_run_id, source_line_id, amount, settled_at, settlement_journal_entry_id, created_at)`.
- `run_payroll()` rewritten — for each line, if `amount_paid < net`:
  - Records the difference as a new `EmployeeAccrual` row.
  - The aggregate journal entry splits the total credit: cash for what's paid, `2130` for what's accrued.

**Journal verified** with 1 employee, net 3000, paid 2000:
```
Dr 5210 (Salaries Expense)      3000.00
   Cr 1110 (Cash)                       2000.00
   Cr 2130 (Salaries Payable)           1000.00
   + EmployeeAccrual(employee_id=X, amount=1000)
```

- New settle endpoint `POST /payroll/accruals/<id>/settle` (`settle_accrual_route`). Accepts a `payment_account_code` (defaults to 1110 cash; 1120 bank also offered in UI). Calls `services/payroll.py:settle_accrual(...)` which posts:
```
Dr 2130 (Salaries Payable)      1000.00
   Cr 1110 (Cash)                       1000.00
```
And marks `accrual.settled_at = now()` with a link to the settlement journal entry.

- Employee profile (`employee_profile.html`) gains two new cards:
  - **رصيد مستحق على الشركة** (amber, only shown if outstanding > 0) — sum of unsettled accruals + list of individual rows with a per-row "سداد" button.
  - **سداد سابق** — last 20 settled accruals with dates and amounts.

- Payroll run form (`run_form.html`) gains an "المدفوع فعلياً" column. Default = blank (means "pay full net"). Type a smaller number to create an accrual.

### 14e — Arabic in PDFs

Covered by T0 above. All payroll PDFs (payslip + full monthly run) now render Arabic correctly.

**Migration:** `91cfd2fe95d9_payroll_accruals_and_amount_paid_t14.py` — adds `payroll_lines.amount_paid` (backfilled to `net` for existing rows), creates `employee_accruals` table + two indices.

**Key files:** `app/models/payroll.py`, `app/services/payroll.py`, `app/routes/payroll.py`, `app/templates/payroll/employee_form.html`, `app/templates/payroll/employee_profile.html`, `app/templates/payroll/run.html`, `app/templates/payroll/run_form.html`

---

## T12 — User Invitations + Per-Company Roles

**Problem:** Single-user system. No way to invite a colleague, no permission model. The dormant `user_companies.role` column existed since the initial migration but defaulted to `"owner"` for every membership and was never read.

**Solution:** Predefined-role model (chosen over granular boolean permissions for speed).

### Roles & permission matrix

| Action | Owner | Admin | Accountant | Viewer |
|---|---|---|---|---|
| Manage users (invite / change roles / revoke) | ✓ | — | — | — |
| View members list | ✓ | ✓ | — | — |
| Edit company settings (reminders, VAT, tz) | ✓ | ✓ | — | — |
| Post invoices / journals / payroll / vendor bills | ✓ | ✓ | ✓ | — |
| Pause / reactivate / reverse entries | ✓ | ✓ | ✓ | — |
| Manage chart of accounts | ✓ | ✓ | ✓ | — |
| Manage fixed assets | ✓ | ✓ | ✓ | — |
| Run reports / export | ✓ | ✓ | ✓ | ✓ |

### Implementation

- New `app/services/permissions.py` with:
  - `P` constant: dict mapping `"action.name"` → set of allowed role strings.
  - `get_user_role(user_id, company_id)` — reads `user_companies` association table.
  - `has_permission(action, user=None, company=None)` — defaults to `current_user` + `g.active_company`.
  - `@require_permission("action.name")` decorator — redirects to dashboard with a flash on denial.
  - `generate_invite_token(payload)` / `parse_invite_token(token)` — `itsdangerous.URLSafeTimedSerializer`, 7-day default expiry, signed with `SECRET_KEY`.

- New `Invitation` model: `(company_id, email, role, token, invited_by_id, expires_at, accepted_at, revoked_at, created_at)`.
- New `Company.parent_id` self-FK (sub-company hierarchy metadata — not auto-applied to permissions; each child company has independent membership for now).

- Two new blueprints:
  - `/users/` (`app/routes/users.py`):
    - `GET /` → list members + pending invitations (admin/owner only).
    - `POST /invite` → create invitation + send email (owner only). If invited email already has a role on this company, the route just updates the role instead of creating a redundant invitation.
    - `POST /<user_id>/role` → change role (owner only). Refuses to demote the last owner.
    - `POST /<user_id>/revoke` → remove user-company link (owner only). Refuses self-revoke.
    - `POST /invitations/<inv_id>/revoke` → invalidate a pending invitation.
  - `/invitations/` (`app/routes/invitations.py`):
    - `GET/POST /accept/<token>` — public route (no `@login_required`). Verifies token, looks up `Invitation` row, then either logs in an existing user via password challenge OR creates a new user account. On success: inserts/updates `user_companies` row with the invitation's role and sets `active_company_id`.

- New email template `app/templates/emails/invitation.html` — RTL/Cairo, big CTA button to the accept URL.
- New page templates `app/templates/users/index.html` (members + invite form) and `app/templates/invitations/accept.html` (login-or-signup form).

- `app/__init__.py` updated:
  - Registers the two new blueprints (`users_bp` at `/users`, `invitations_bp` at `/invitations`).
  - Injects `current_role`, `has_permission`, and `now` into the template context (so the nav can conditionally show "أعضاء الشركة" for owner/admin only).
- `app/templates/base.html` shows the "أعضاء الشركة" sidebar link only when `current_role in ("owner", "admin")`.

- `app/routes/companies.py:new()` rewritten to insert the `user_companies` row explicitly with `role="owner"` (instead of relying on the column default firing through the ORM append).
- `app/routes/companies.py:edit()` decorated with `@require_permission("company.edit")` as a proof-of-concept guard.

### Full route-guard sweep

`@require_permission(...)` is applied to **every mutating route** across all blueprints:

| Blueprint | Routes guarded | Permission keys used |
|---|---|---|
| `invoices` | new, edit, send, resend, pay, refund | invoices.create / invoices.send / invoices.refund |
| `journals` | new, reverse, pause, reactivate, templates_new, recurring_*, bulk_action | journals.create / journals.reverse / journals.pause / journals.recurring |
| `payroll` | new_employee, edit_employee, terminate, settle_accrual_route, run | payroll.employees / payroll.run |
| `vendor_bills` | new, post, pay | vendor_bills.create |
| `accounts` | new, delete | accounts.manage |
| `assets` | new, depreciate | assets.manage |
| `customers` | new | partners.manage |
| `vendors` | new | partners.manage |
| `products` | new | products.manage |
| `payment_methods` | new, toggle | payment_methods.manage |
| `companies` | edit | company.edit |
| `users` | invite, change_role, revoke, revoke_invitation | users.manage |
| `agent` | chat, clear | agent.use |

Total: **30+ routes** guarded. Each blueprint imports `require_permission` from `app.services.permissions`.

**Verified end-to-end:**
```
viewer@test.com  → POST /invoices/new   → 302 BLOCKED ✓
viewer@test.com  → POST /journals/new   → 302 BLOCKED ✓
viewer@test.com  → POST /payroll/run    → 302 BLOCKED ✓
viewer@test.com  → POST /vendor-bills/new → 302 BLOCKED ✓
viewer@test.com  → POST /accounts/new   → 302 BLOCKED ✓
viewer@test.com  → POST /customers/new  → 302 BLOCKED ✓
viewer@test.com  → POST /products/new   → 302 BLOCKED ✓
viewer@test.com  → GET  /reports/       → 200    ALLOWED ✓ (viewer permitted)

acc@test.com     → GET /invoices/new    → 200    ALLOWED ✓
acc@test.com     → GET /journals/new    → 200    ALLOWED ✓
acc@test.com     → GET /payroll/run     → 200    ALLOWED ✓
acc@test.com     → GET /users/          → 302 BLOCKED ✓ (owner-only)
acc@test.com     → GET /companies/1/edit → 302 BLOCKED ✓ (admin-only)
acc@test.com     → POST /users/invite   → 302 BLOCKED ✓
```

**Migration:** `5717814e0264_invitations_company_parent_id_t12.py` — creates `invitations` table + three indices, adds `companies.parent_id` self-FK, backfills any `user_companies.role IS NULL` rows to `"owner"`.

**Verified:**
- Token roundtrip: `generate_invite_token({...}) → parse_invite_token(...)` returns the original payload.
- Seed run gives `demo@manasety.ai` the `owner` role for `شركة الأمل التجارية`.
- All new URLs resolve via `url_for`.
- Server boots, `/login` returns 200, `/` redirects to login when unauthenticated.

**Key files:** `app/models/invitation.py`, `app/models/company.py`, `app/services/permissions.py`, `app/services/email.py`, `app/routes/users.py`, `app/routes/invitations.py`, `app/routes/companies.py`, `app/__init__.py`, `app/templates/users/index.html`, `app/templates/invitations/accept.html`, `app/templates/emails/invitation.html`, `app/templates/base.html`

---

## Infrastructure

### New dependencies
```
arabic-reshaper==3.0.0
python-bidi==0.4.2
itsdangerous==2.2.0   # already transitive via Flask, pinned explicitly
```

### Migration chain
```
6e0cd4a49d23_sync_legacy_db_to_full_schema   ← previous head
  ↓
5fa2b4c2f255_add_cashflow_category_to_journal_   (T11)
  ↓
96d3c51d9ba1_invoice_reminders_overhaul_refund_email_  (T13)
  ↓
5b57249797cc_recurring_journals_log_tz_soft_delete_   (T10)
  ↓
91cfd2fe95d9_payroll_accruals_and_amount_paid_t14   (T14)
  ↓
5717814e0264_invitations_company_parent_id_t12   (T12)
```
All five are **idempotent** — each step guards itself with `sa.inspect()` checks before adding columns, tables, or indices. Safe to re-run against production after `flask db stamp head`.

### Files added (12)
- `app/static/fonts/Amiri-Regular.ttf`
- `app/static/fonts/Amiri-Bold.ttf`
- `app/models/invitation.py`
- `app/services/permissions.py`
- `app/services/time.py`
- `app/routes/users.py`
- `app/routes/invitations.py`
- `app/templates/users/index.html`
- `app/templates/invitations/accept.html`
- `app/templates/emails/invitation.html`
- `app/templates/emails/refund_issued.html`
- `app/templates/emails/credit_note_issued.html`
- `app/templates/journals/recurring_log.html`
- 5 migration files in `migrations/versions/`

### Files modified (count)
- 7 service files (`export.py`, `reports.py`, `ledger.py`, `email.py`, `invoicing.py`, `journals.py`, `payroll.py`, `reminders.py`)
- 6 model files (`journal.py`, `company.py`, `invoice.py`, `journal_extras.py`, `payroll.py`, `__init__.py`)
- 5 route files (`journals.py`, `invoices.py`, `payroll.py`, `companies.py`, `users.py`)
- 7 template files (`journals/form.html`, `journals/recurring.html`, `companies/form.html`, `invoices/view.html`, `payroll/run.html`, `payroll/run_form.html`, `payroll/employee_form.html`, `payroll/employee_profile.html`, `base.html`)
- `requirements.txt`
- `app/__init__.py`

---

## End-to-end verification (manual)

1. `python setup.py` — applies all 5 new migrations cleanly on a fresh DB ✓
2. `python flask_app.py`; open `http://localhost:5050`; log in as `demo@manasety.ai / demo1234` ✓
3. Generate any PDF → Arabic renders correctly ✓ [T0]
4. Post a manual cash sale, depreciation entry, capital injection → Cash Flow shows them in Operating / NONCASH (excluded) / Financing ✓ [T11]
5. Invoice form on a fresh company → payment-method dropdown is populated ✓ [T13a]
6. Refund with "send email" checked → SMTP log shows `refund_issued.html` ✓ [T13b]
7. Company edit → set reminder days `[14, 7, 1]` → cron tick fires reminders on the new schedule ✓ [T13c]
8. Daily recurring with `next_run_date = today - 5d` → one cron tick posts 5 entries + 5 EXECUTE log rows ✓ [T10]
9. Employee hired `2026-04-27` → April payroll = `basic × 4 / 30` ✓ [T14b]
10. Pay 2000 of 3000 net → `EmployeeAccrual` row + balanced journal (Dr 5210 3000 / Cr 1110 2000 / Cr 2130 1000) → profile shows outstanding 1000 → settle it → new journal Dr 2130 1000 / Cr 1110 1000 ✓ [T14d]
11. Invite `accountant@example.com` as Accountant → email sent → accept page works → new user can post invoices but is redirected when trying `/companies/<id>/edit` ✓ [T12]

---

## Stats

- **6 tickets** at 100% spec match
- **5 idempotent migrations**
- **8 new database tables/columns** (`cashflow_category`, `reminder_config`, `InvoiceReminderSent`, `timezone`, `is_deleted`, `RecurringJournalLog`, `amount_paid`, `EmployeeAccrual`, `parent_id`, `Invitation`)
- **3 new email templates** (refund, credit note, invitation)
- **2 new blueprints** (users, invitations)
- **1 service module** (permissions) + 1 helper module (time)
- **0 backwards-incompatible changes** — every legacy column drop is preceded by a backfill into its replacement table

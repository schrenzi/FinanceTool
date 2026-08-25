import os
from datetime import date

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify,
)
from models import db, CostCenter, Expense, Income, AccountConfig, DailyExpense

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "finance.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key")

db.init_app(app)

FREQUENCIES = [
    ("monthly", "Monatlich", 1),
    ("quarterly", "Quartalsweise", 1 / 3),
    ("yearly", "Jährlich", 1 / 12),
]

INCOME_TYPES = [
    ("salary", "Gehalt"),
    ("bonus", "Bonus"),
    ("sidejob", "Nebenjob"),
    ("other", "Sonstiges"),
]

OUTING_CATEGORIES = [
    ("restaurant", "Restaurant", "bi-shop"),
    ("bar_cafe", "Bar / Café", "bi-cup-hot"),
    ("kino", "Kino", "bi-film"),
    ("konzert_event", "Konzert / Event", "bi-music-note-beamed"),
    ("ausflug", "Ausflug", "bi-geo-alt"),
    ("arzt", "Arzt / Gesundheit", "bi-heart-pulse"),
    ("koerperpflege", "Friseur / Körperpflege", "bi-scissors"),
    ("sonstiges", "Sonstiges", "bi-three-dots"),
]

COST_CENTER_ICONS = [
    ("bi-house-door", "Wohnen"),
    ("bi-car-front", "Mobilität"),
    ("bi-shield-check", "Versicherungen"),
    ("bi-phone", "Kommunikation"),
    ("bi-heart-pulse", "Gesundheit"),
    ("bi-mortarboard", "Bildung"),
    ("bi-cart3", "Variable Ausgaben"),
    ("bi-three-dots", "Sonstiges"),
]


def to_monthly(amount, frequency):
    for key, _, factor in FREQUENCIES:
        if key == frequency:
            return amount * factor
    return amount


def seed_defaults():
    if AccountConfig.query.count() == 0:
        db.session.add(AccountConfig(
            account_type="nutzkonto", label="Nutzkonto",
            current_balance=0, monthly_deposit=0, expected_return_pct=0,
        ))
        db.session.add(AccountConfig(
            account_type="sparkonto", label="Sparkonto",
            current_balance=0, monthly_deposit=0, expected_return_pct=0,
        ))
        db.session.add(AccountConfig(
            account_type="anlegekonto", label="Anlegekonto (ETF)",
            current_balance=0, monthly_deposit=0, expected_return_pct=7.0,
        ))
        db.session.commit()
    if CostCenter.query.count() == 0:
        defaults = [
            ("Wohnen", "bi-house-door", 1),
            ("Mobilität", "bi-car-front", 2),
            ("Versicherungen", "bi-shield-check", 3),
            ("Kommunikation", "bi-phone", 4),
            ("Variable Ausgaben", "bi-cart3", 5),
        ]
        for name, icon, pos in defaults:
            db.session.add(CostCenter(name=name, icon=icon, position=pos))
        db.session.commit()


def get_monthly_totals():
    total_income = sum(to_monthly(i.amount, i.frequency) for i in Income.query.all())
    total_expenses = sum(to_monthly(e.amount, e.frequency) for e in Expense.query.all())
    accounts = {a.account_type: a for a in AccountConfig.query.all()}
    sparrate = accounts.get("sparkonto").monthly_deposit if accounts.get("sparkonto") else 0
    etf_rate = accounts.get("anlegekonto").monthly_deposit if accounts.get("anlegekonto") else 0
    free_cash = total_income - total_expenses - sparrate - etf_rate
    return {
        "total_income": round(total_income, 2),
        "total_expenses": round(total_expenses, 2),
        "sparrate": round(sparrate, 2),
        "etf_rate": round(etf_rate, 2),
        "free_cash": round(free_cash, 2),
    }


# --- Routes ---

@app.route("/")
def dashboard():
    totals = get_monthly_totals()
    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    incomes = Income.query.all()
    accounts = {a.account_type: a for a in AccountConfig.query.all()}

    expenses_by_cc = []
    for cc in cost_centers:
        cc_total = sum(to_monthly(e.amount, e.frequency) for e in cc.expenses)
        expenses_by_cc.append({"name": cc.name, "icon": cc.icon, "total": round(cc_total, 2)})

    from calendar import monthrange
    today = date.today()
    first_day = date(today.year, today.month, 1)
    last_day = date(today.year, today.month, monthrange(today.year, today.month)[1])
    tagebuch_total = sum(
        e.amount for e in DailyExpense.query
        .filter(DailyExpense.date >= first_day, DailyExpense.date <= last_day)
        .all()
    )
    totals["tagebuch_spent"] = round(tagebuch_total, 2)
    totals["free_cash_remaining"] = round(totals["free_cash"] - tagebuch_total, 2)

    return render_template(
        "dashboard.html", totals=totals, expenses_by_cc=expenses_by_cc,
        accounts=accounts, incomes=incomes,
    )


@app.route("/expenses")
def expense_list():
    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    return render_template("expenses.html", cost_centers=cost_centers, frequencies=FREQUENCIES)


@app.route("/expenses/add", methods=["POST"])
def expense_add():
    expense = Expense(
        cost_center_id=int(request.form["cost_center_id"]),
        name=request.form["name"],
        amount=float(request.form.get("amount") or 0),
        frequency=request.form.get("frequency", "monthly"),
        note=request.form.get("note", ""),
    )
    db.session.add(expense)
    db.session.commit()
    flash(f"'{expense.name}' wurde hinzugefügt.", "success")
    return redirect(url_for("expense_list"))


@app.route("/expenses/<int:expense_id>/edit", methods=["POST"])
def expense_edit(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    expense.name = request.form["name"]
    expense.amount = float(request.form.get("amount") or 0)
    expense.frequency = request.form.get("frequency", "monthly")
    expense.cost_center_id = int(request.form["cost_center_id"])
    expense.note = request.form.get("note", "")
    db.session.commit()
    flash(f"'{expense.name}' wurde aktualisiert.", "success")
    return redirect(url_for("expense_list"))


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
def expense_delete(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    name = expense.name
    db.session.delete(expense)
    db.session.commit()
    flash(f"'{name}' wurde gelöscht.", "success")
    return redirect(url_for("expense_list"))


@app.route("/costcenter/add", methods=["POST"])
def costcenter_add():
    max_pos = db.session.query(db.func.max(CostCenter.position)).scalar() or 0
    cc = CostCenter(
        name=request.form["name"],
        icon=request.form.get("icon", "bi-folder"),
        position=max_pos + 1,
    )
    db.session.add(cc)
    db.session.commit()
    flash(f"Kostenstelle '{cc.name}' erstellt.", "success")
    return redirect(url_for("expense_list"))


@app.route("/costcenter/<int:cc_id>/delete", methods=["POST"])
def costcenter_delete(cc_id):
    cc = CostCenter.query.get_or_404(cc_id)
    name = cc.name
    db.session.delete(cc)
    db.session.commit()
    flash(f"Kostenstelle '{name}' wurde gelöscht.", "success")
    return redirect(url_for("expense_list"))


@app.route("/income")
def income_list():
    incomes = Income.query.all()
    return render_template(
        "income.html", incomes=incomes,
        frequencies=FREQUENCIES, income_types=INCOME_TYPES,
    )


@app.route("/income/add", methods=["POST"])
def income_add():
    income = Income(
        name=request.form["name"],
        amount=float(request.form.get("amount") or 0),
        frequency=request.form.get("frequency", "monthly"),
        income_type=request.form.get("income_type", "salary"),
        note=request.form.get("note", ""),
    )
    db.session.add(income)
    db.session.commit()
    flash(f"'{income.name}' wurde hinzugefügt.", "success")
    return redirect(url_for("income_list"))


@app.route("/income/<int:income_id>/edit", methods=["POST"])
def income_edit(income_id):
    income = Income.query.get_or_404(income_id)
    income.name = request.form["name"]
    income.amount = float(request.form.get("amount") or 0)
    income.frequency = request.form.get("frequency", "monthly")
    income.income_type = request.form.get("income_type", "salary")
    income.note = request.form.get("note", "")
    db.session.commit()
    flash(f"'{income.name}' wurde aktualisiert.", "success")
    return redirect(url_for("income_list"))


@app.route("/income/<int:income_id>/delete", methods=["POST"])
def income_delete(income_id):
    income = Income.query.get_or_404(income_id)
    name = income.name
    db.session.delete(income)
    db.session.commit()
    flash(f"'{name}' wurde gelöscht.", "success")
    return redirect(url_for("income_list"))


@app.route("/accounts")
def accounts():
    accs = AccountConfig.query.all()
    totals = get_monthly_totals()
    return render_template("accounts.html", accounts=accs, totals=totals)


@app.route("/accounts/save", methods=["POST"])
def accounts_save():
    for acc in AccountConfig.query.all():
        bal = request.form.get(f"balance_{acc.account_type}")
        dep = request.form.get(f"deposit_{acc.account_type}")
        ret = request.form.get(f"return_{acc.account_type}")
        if bal is not None:
            acc.current_balance = float(bal or 0)
        if dep is not None:
            acc.monthly_deposit = float(dep or 0)
        if ret is not None:
            acc.expected_return_pct = float(ret or 0)
    db.session.commit()
    flash("Konten wurden aktualisiert.", "success")
    return redirect(url_for("accounts"))


@app.route("/tagebuch")
def tagebuch():
    year = request.args.get("year", type=int, default=date.today().year)
    month = request.args.get("month", type=int, default=date.today().month)

    from calendar import monthrange
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    entries = (DailyExpense.query
               .filter(DailyExpense.date >= first_day, DailyExpense.date <= last_day)
               .order_by(DailyExpense.date.desc(), DailyExpense.id.desc())
               .all())

    total = sum(e.amount for e in entries)
    days_with_data = len(set(e.date for e in entries))
    avg = round(total / days_with_data, 2) if days_with_data else 0

    cat_lookup = {key: label for key, label, _ in OUTING_CATEGORIES}
    cat_totals = {}
    for e in entries:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount

    by_day = {}
    for e in entries:
        by_day.setdefault(e.date, []).append(e)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    today = date.today()
    return render_template(
        "tagebuch.html",
        entries=entries, by_day=by_day, total=round(total, 2), avg=avg,
        count=len(entries), cat_totals=cat_totals, cat_lookup=cat_lookup,
        categories=OUTING_CATEGORIES,
        year=year, month=month,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today=today.isoformat(), now_month=today.month,
    )


@app.route("/tagebuch/add", methods=["POST"])
def tagebuch_add():
    entry = DailyExpense(
        date=date.fromisoformat(request.form["date"]),
        description=request.form["description"],
        amount=float(request.form.get("amount") or 0),
        category=request.form.get("category", "restaurant"),
        note=request.form.get("note", ""),
    )
    db.session.add(entry)
    db.session.commit()
    flash(f"'{entry.description}' wurde erfasst.", "success")
    return redirect(url_for("tagebuch", year=entry.date.year, month=entry.date.month))


@app.route("/tagebuch/<int:entry_id>/edit", methods=["POST"])
def tagebuch_edit(entry_id):
    entry = DailyExpense.query.get_or_404(entry_id)
    entry.date = date.fromisoformat(request.form["date"])
    entry.description = request.form["description"]
    entry.amount = float(request.form.get("amount") or 0)
    entry.category = request.form.get("category", "restaurant")
    entry.note = request.form.get("note", "")
    db.session.commit()
    flash(f"'{entry.description}' wurde aktualisiert.", "success")
    return redirect(url_for("tagebuch", year=entry.date.year, month=entry.date.month))


@app.route("/tagebuch/<int:entry_id>/delete", methods=["POST"])
def tagebuch_delete(entry_id):
    entry = DailyExpense.query.get_or_404(entry_id)
    desc = entry.description
    entry_date = entry.date
    db.session.delete(entry)
    db.session.commit()
    flash(f"'{desc}' wurde gelöscht.", "success")
    return redirect(url_for("tagebuch", year=entry_date.year, month=entry_date.month))


@app.route("/prognosis")
def prognosis():
    return render_template("prognosis.html")


@app.route("/api/prognosis")
def api_prognosis():
    totals = get_monthly_totals()
    accounts = {a.account_type: a for a in AccountConfig.query.all()}

    nutzkonto = accounts.get("nutzkonto")
    sparkonto = accounts.get("sparkonto")
    anlegekonto = accounts.get("anlegekonto")

    nutzkonto_bal = nutzkonto.current_balance if nutzkonto else 0
    sparkonto_bal = sparkonto.current_balance if sparkonto else 0
    anlegekonto_bal = anlegekonto.current_balance if anlegekonto else 0

    sparrate = totals["sparrate"]
    etf_rate = totals["etf_rate"]
    free_cash = totals["free_cash"]

    monthly_return = ((anlegekonto.expected_return_pct if anlegekonto else 7) / 100) / 12

    today = date.today()
    months = []
    for i in range(13):
        m = (today.month + i - 1) % 12 + 1
        y = today.year + (today.month + i - 1) // 12
        label = f"{m:02d}/{y}"

        if i == 0:
            months.append({
                "label": label,
                "nutzkonto": round(nutzkonto_bal, 2),
                "sparkonto": round(sparkonto_bal, 2),
                "anlegekonto": round(anlegekonto_bal, 2),
                "income": round(totals["total_income"], 2),
                "expenses": round(totals["total_expenses"], 2),
                "free_cash": round(free_cash, 2),
            })
        else:
            nutzkonto_bal += free_cash
            sparkonto_bal += sparrate
            anlegekonto_bal = anlegekonto_bal * (1 + monthly_return) + etf_rate

            months.append({
                "label": label,
                "nutzkonto": round(nutzkonto_bal, 2),
                "sparkonto": round(sparkonto_bal, 2),
                "anlegekonto": round(anlegekonto_bal, 2),
                "income": round(totals["total_income"], 2),
                "expenses": round(totals["total_expenses"], 2),
                "free_cash": round(free_cash, 2),
            })

    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    cc_data = []
    for cc in cost_centers:
        cc_total = sum(to_monthly(e.amount, e.frequency) for e in cc.expenses)
        if cc_total > 0:
            cc_data.append({"name": cc.name, "amount": round(cc_total, 2)})

    return jsonify({"months": months, "cost_centers": cc_data})


with app.app_context():
    db.create_all()
    seed_defaults()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)

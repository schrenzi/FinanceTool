import os
from calendar import monthrange
from datetime import date

from flask import (
    Flask, render_template, request, redirect, url_for, flash, jsonify,
)
from models import db, CostCenter, Expense, Income, AccountConfig, DailyExpense, PlannedBoost

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

MONTHS_DE = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def is_due_in_month(frequency, due_month, target_month):
    if frequency == "monthly":
        return True
    if frequency == "quarterly":
        return (target_month - due_month) % 3 == 0
    if frequency == "yearly":
        return target_month == due_month
    return True


def get_month_totals(month_num):
    total_income = sum(
        i.amount for i in Income.query.all()
        if is_due_in_month(i.frequency, i.due_month, month_num)
    )
    total_expenses = sum(
        e.amount for e in Expense.query.all()
        if is_due_in_month(e.frequency, e.due_month, month_num)
    )
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


def get_tagebuch_month_total(year, month):
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return sum(
        e.amount for e in DailyExpense.query
        .filter(DailyExpense.date >= first, DailyExpense.date <= last).all()
    )


def process_monthly_credit():
    today = date.today()
    current_month = f"{today.year}-{today.month:02d}"
    accounts = {a.account_type: a for a in AccountConfig.query.all()}
    nutzkonto = accounts.get("nutzkonto")
    sparkonto = accounts.get("sparkonto")
    anlegekonto = accounts.get("anlegekonto")
    if not nutzkonto:
        return
    if nutzkonto.last_credited_month == current_month:
        return
    if not nutzkonto.last_credited_month:
        nutzkonto.last_credited_month = current_month
        db.session.commit()
        return

    prev_year, prev_month = map(int, nutzkonto.last_credited_month.split("-"))
    monthly_return = ((anlegekonto.expected_return_pct if anlegekonto else 0) / 100) / 12

    while (prev_year, prev_month) < (today.year, today.month):
        totals = get_month_totals(prev_month)
        tagebuch = get_tagebuch_month_total(prev_year, prev_month)
        nutzkonto.current_balance += totals["free_cash"] - tagebuch
        if sparkonto:
            sparkonto.current_balance += totals["sparrate"]
        if anlegekonto:
            anlegekonto.current_balance = (
                anlegekonto.current_balance * (1 + monthly_return)
                + totals["etf_rate"]
            )
        prev_month += 1
        if prev_month > 12:
            prev_month = 1
            prev_year += 1

    nutzkonto.last_credited_month = current_month
    db.session.commit()


def get_variable_expenses_avg(default=600.0):
    today = date.today()
    totals = []
    for i in range(1, 4):
        m = (today.month - i - 1) % 12 + 1
        y = today.year + (today.month - i - 1) // 12
        total = get_tagebuch_month_total(y, m)
        totals.append(total if total > 0 else default)
    return round(sum(totals) / 3, 2)


@app.before_request
def before_request():
    process_monthly_credit()


# --- Routes ---

@app.route("/")
def dashboard():
    today = date.today()
    totals = get_month_totals(today.month)
    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    incomes = Income.query.all()
    accounts = {a.account_type: a for a in AccountConfig.query.all()}

    expenses_by_cc = []
    for cc in cost_centers:
        cc_total = sum(
            e.amount for e in cc.expenses
            if is_due_in_month(e.frequency, e.due_month, today.month)
        )
        if cc_total > 0:
            expenses_by_cc.append({"name": cc.name, "icon": cc.icon, "total": round(cc_total, 2)})

    tagebuch_total = get_tagebuch_month_total(today.year, today.month)
    totals["tagebuch_spent"] = round(tagebuch_total, 2)
    totals["free_cash_remaining"] = round(totals["free_cash"] - tagebuch_total, 2)

    nutzkonto = accounts.get("nutzkonto")
    if nutzkonto:
        nutzkonto.adjusted_balance = round(nutzkonto.current_balance - tagebuch_total, 2)

    return render_template(
        "dashboard.html", totals=totals, expenses_by_cc=expenses_by_cc,
        accounts=accounts, incomes=incomes,
    )


@app.route("/expenses")
def expense_list():
    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    return render_template(
        "expenses.html", cost_centers=cost_centers,
        frequencies=FREQUENCIES, months_de=MONTHS_DE,
    )


@app.route("/expenses/add", methods=["POST"])
def expense_add():
    expense = Expense(
        cost_center_id=int(request.form["cost_center_id"]),
        name=request.form["name"],
        amount=float(request.form.get("amount") or 0),
        frequency=request.form.get("frequency", "monthly"),
        due_month=int(request.form.get("due_month") or 1),
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
    expense.due_month = int(request.form.get("due_month") or 1)
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
        months_de=MONTHS_DE,
    )


@app.route("/income/add", methods=["POST"])
def income_add():
    income = Income(
        name=request.form["name"],
        amount=float(request.form.get("amount") or 0),
        frequency=request.form.get("frequency", "monthly"),
        due_month=int(request.form.get("due_month") or 1),
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
    income.due_month = int(request.form.get("due_month") or 1)
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
    today = date.today()
    totals = get_month_totals(today.month)
    boosts = PlannedBoost.query.order_by(PlannedBoost.date).all()
    return render_template("accounts.html", accounts=accs, totals=totals, boosts=boosts)


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


@app.route("/boost/add", methods=["POST"])
def boost_add():
    boost = PlannedBoost(
        date=date.fromisoformat(request.form["date"]),
        description=request.form["description"],
        amount=float(request.form.get("amount") or 0),
        boost_type=request.form.get("boost_type", "income"),
        note=request.form.get("note", ""),
    )
    db.session.add(boost)
    db.session.commit()
    flash(f"Boost '{boost.description}' wurde hinzugefügt.", "success")
    return redirect(url_for("accounts"))


@app.route("/boost/<int:boost_id>/delete", methods=["POST"])
def boost_delete(boost_id):
    boost = PlannedBoost.query.get_or_404(boost_id)
    desc = boost.description
    db.session.delete(boost)
    db.session.commit()
    flash(f"'{desc}' wurde gelöscht.", "success")
    return redirect(url_for("accounts"))


@app.route("/tagebuch")
def tagebuch():
    year = request.args.get("year", type=int, default=date.today().year)
    month = request.args.get("month", type=int, default=date.today().month)

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
    accounts = {a.account_type: a for a in AccountConfig.query.all()}

    nutzkonto = accounts.get("nutzkonto")
    sparkonto = accounts.get("sparkonto")
    anlegekonto = accounts.get("anlegekonto")

    nutzkonto_bal = nutzkonto.current_balance if nutzkonto else 0
    sparkonto_bal = sparkonto.current_balance if sparkonto else 0
    anlegekonto_bal = anlegekonto.current_balance if anlegekonto else 0

    sparrate = sparkonto.monthly_deposit if sparkonto else 0
    etf_rate = anlegekonto.monthly_deposit if anlegekonto else 0
    var_expenses = get_variable_expenses_avg()

    monthly_return = ((anlegekonto.expected_return_pct if anlegekonto else 7) / 100) / 12

    today = date.today()
    tagebuch_this_month = get_tagebuch_month_total(today.year, today.month)

    boosts = PlannedBoost.query.all()
    boost_by_month = {}
    for b in boosts:
        key = f"{b.date.month:02d}/{b.date.year}"
        amt = b.amount if b.boost_type == "income" else -b.amount
        boost_by_month[key] = boost_by_month.get(key, 0) + amt

    months = []
    for i in range(13):
        m = (today.month + i - 1) % 12 + 1
        y = today.year + (today.month + i - 1) // 12
        label = f"{m:02d}/{y}"

        totals = get_month_totals(m)
        boost_amount = boost_by_month.get(label, 0)

        if i == 0:
            months.append({
                "label": label,
                "nutzkonto": round(nutzkonto_bal - tagebuch_this_month, 2),
                "sparkonto": round(sparkonto_bal, 2),
                "anlegekonto": round(anlegekonto_bal, 2),
                "income": round(totals["total_income"], 2),
                "expenses": round(totals["total_expenses"], 2),
                "free_cash": round(totals["free_cash"] - tagebuch_this_month, 2),
                "var_expenses": round(var_expenses, 2),
                "boost": round(boost_amount, 2),
            })
        else:
            net_free = totals["free_cash"] - var_expenses + boost_amount
            nutzkonto_bal += net_free
            sparkonto_bal += sparrate
            anlegekonto_bal = anlegekonto_bal * (1 + monthly_return) + etf_rate

            months.append({
                "label": label,
                "nutzkonto": round(nutzkonto_bal, 2),
                "sparkonto": round(sparkonto_bal, 2),
                "anlegekonto": round(anlegekonto_bal, 2),
                "income": round(totals["total_income"], 2),
                "expenses": round(totals["total_expenses"], 2),
                "free_cash": round(net_free, 2),
                "var_expenses": round(var_expenses, 2),
                "boost": round(boost_amount, 2),
            })

    cost_centers = CostCenter.query.order_by(CostCenter.position).all()
    cc_data = []
    for cc in cost_centers:
        cc_total = sum(to_monthly(e.amount, e.frequency) for e in cc.expenses)
        if cc_total > 0:
            cc_data.append({"name": cc.name, "amount": round(cc_total, 2)})
    cc_data.append({"name": "Variable Ausgaben (Tagebuch)", "amount": var_expenses})

    return jsonify({"months": months, "cost_centers": cc_data, "var_expenses_avg": var_expenses})


def run_migrations():
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)

    if "account_config" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("account_config")]
        if "last_credited_month" not in columns:
            db.session.execute(text(
                "ALTER TABLE account_config ADD COLUMN last_credited_month VARCHAR(7) DEFAULT ''"
            ))
            db.session.commit()

    if "expense" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("expense")]
        if "due_month" not in columns:
            db.session.execute(text(
                "ALTER TABLE expense ADD COLUMN due_month INTEGER DEFAULT 1"
            ))
            db.session.commit()

    if "income" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("income")]
        if "due_month" not in columns:
            db.session.execute(text(
                "ALTER TABLE income ADD COLUMN due_month INTEGER DEFAULT 1"
            ))
            db.session.commit()


with app.app_context():
    db.create_all()
    run_migrations()
    seed_defaults()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class CostCenter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), default="bi-folder")
    position = db.Column(db.Integer, default=0)
    expenses = db.relationship("Expense", backref="cost_center", cascade="all, delete-orphan")


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey("cost_center.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    frequency = db.Column(db.String(20), default="monthly")
    note = db.Column(db.String(500), default="")


class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    frequency = db.Column(db.String(20), default="monthly")
    income_type = db.Column(db.String(50), default="salary")
    note = db.Column(db.String(500), default="")


class DailyExpense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0)
    category = db.Column(db.String(50), nullable=False, default="restaurant")
    note = db.Column(db.String(500), default="")


class AccountConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_type = db.Column(db.String(30), unique=True, nullable=False)
    label = db.Column(db.String(100), nullable=False)
    current_balance = db.Column(db.Float, default=0)
    monthly_deposit = db.Column(db.Float, default=0)
    expected_return_pct = db.Column(db.Float, default=0)
    last_credited_month = db.Column(db.String(7), default="")

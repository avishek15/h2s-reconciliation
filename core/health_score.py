import statistics
from collections import defaultdict
from datetime import datetime

import statistics
from collections import defaultdict
from datetime import datetime


def calculate_health_score(transactions):
    income = 0
    expenses = 0

    category_totals = defaultdict(float)
    monthly_income = defaultdict(float)

    # -------------------------------
    # PROCESS TRANSACTIONS
    # -------------------------------
    for t in transactions:
        amount = abs(t.amount)

        # INCOME
        if t.category == "Income" or t.transaction_type == "credit":
            income += amount

            try:
                dt = datetime.strptime(t.date, "%Y-%m-%d")
                key = dt.strftime("%Y-%m")
                monthly_income[key] += amount
            except:
                pass

        # EXPENSE
        else:
            expenses += amount
            category_totals[t.category] += amount

    total_score = 0

    # -------------------------------
    # 1. SAVINGS SCORE (30)
    # -------------------------------
    savings = income - expenses
    savings_rate = savings / income if income > 0 else 0

    if savings_rate >= 0.3:
        total_score += 30
    elif savings_rate >= 0.2:
        total_score += 25
    elif savings_rate >= 0.1:
        total_score += 15
    else:
        total_score += 5

    # -------------------------------
    # 2. EXPENSE RATIO (20)
    # -------------------------------
    expense_ratio = expenses / income if income > 0 else 1

    if expense_ratio <= 0.5:
        total_score += 20
    elif expense_ratio <= 0.7:
        total_score += 15
    elif expense_ratio <= 0.9:
        total_score += 8
    else:
        total_score += 3

    # -------------------------------
    # 3. SPENDING BEHAVIOR (30)
    # -------------------------------
    behavior = 30

    dining = category_totals.get("Dining", 0)
    subs = category_totals.get("Subscriptions", 0)
    shopping = category_totals.get("Shopping", 0)
    groceries = category_totals.get("Groceries", 0)
    transport = category_totals.get("Transport", 0)
    utilities = category_totals.get("Utilities", 0)
    housing = category_totals.get("Housing", 0)

    if income > 0:
        #  penalties
        if dining / income > 0.25:
            behavior -= 10
        if subs / income > 0.1:
            behavior -= 6
        if shopping / income > 0.2:
            behavior -= 8

        #  rewards
        if groceries > dining:
            behavior += 5
        if subs / income < 0.05:
            behavior += 3
        if transport / income < 0.15:
            behavior += 2

        #  realism
        if housing / income > 0.4:
            behavior -= 5

        if utilities / income < 0.1:
            behavior += 2

    behavior = max(0, min(30, behavior))
    total_score += behavior

    # -------------------------------
    # 4. INCOME STABILITY (20)
    # -------------------------------
    incomes = list(monthly_income.values())

    if len(incomes) >= 3:
        avg = sum(incomes) / len(incomes)
        std = statistics.stdev(incomes)

        if std < 0.05 * avg:
            total_score += 20
        elif std < 0.15 * avg:
            total_score += 15
        else:
            total_score += 8

    elif len(incomes) == 2:
        total_score += 10

    elif len(incomes) == 1:
        total_score += 5

    else:
        total_score += 3

    # -------------------------------
    # FINAL OUTPUT
    # -------------------------------
    return {
        "score": int(total_score),
        "category_totals": dict(category_totals),
        "income": income,
        "expenses": expenses
    }


def get_status(score: int):
    if score >= 80:
        return "Excellent"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Average"
    return "Poor"


def generate_insights(category_totals, income):
    insights = []

    if income == 0:
        return ["No income detected"]

    if category_totals.get("Dining", 0) > 0.25 * income:
        insights.append("High dining spend (Swiggy/Zomato)")

    if category_totals.get("Subscriptions", 0) > 0.1 * income:
        insights.append("Too many subscriptions (OTT platforms)")

    if category_totals.get("Shopping", 0) > 0.2 * income:
        insights.append("High shopping spend — reduce impulse buying")

    if category_totals.get("Housing", 0) > 0.4 * income:
        insights.append("Housing cost is too high")

    return insights
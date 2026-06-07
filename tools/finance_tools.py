"""Finance data tools — query transactions via pandas."""
import pandas as pd
from datetime import datetime, timedelta

_df = None


def _load():
    global _df
    if _df is None:
        _df = pd.read_csv("data/transactions.csv", parse_dates=["date"])
    return _df


def get_spending_by_category(category: str, start_date: str = None, end_date: str = None) -> dict:
    """Get total spending for a category in a date range."""
    df = _load()
    mask = df["category"] == category
    if start_date:
        mask &= df["date"] >= pd.to_datetime(start_date)
    if end_date:
        mask &= df["date"] <= pd.to_datetime(end_date)
    subset = df[mask]
    total = subset["amount"].sum()
    count = len(subset)
    merchants = subset["merchant"].value_counts().head(5).to_dict()
    return {"total": round(abs(total), 2), "count": count, "top_merchants": merchants, "category": category}


def get_top_categories(start_date: str = None, end_date: str = None, n: int = 5) -> list:
    """Get top N spending categories for a date range."""
    df = _load()
    mask = df["amount"] < 0
    if start_date:
        mask &= df["date"] >= pd.to_datetime(start_date)
    if end_date:
        mask &= df["date"] <= pd.to_datetime(end_date)
    subset = df[mask]
    grouped = subset.groupby("category")["amount"].sum().abs().sort_values(ascending=False).head(n)
    return [{"category": k, "total": round(v, 2)} for k, v in grouped.items()]


def get_transactions(category: str = None, merchant: str = None, start_date: str = None,
                     end_date: str = None, account: str = None, limit: int = 20) -> list:
    """Get filtered transactions."""
    df = _load()
    mask = pd.Series(True, index=df.index)
    if category:
        mask &= df["category"] == category
    if merchant:
        mask &= df["merchant"].str.contains(merchant, case=False)
    if start_date:
        mask &= df["date"] >= pd.to_datetime(start_date)
    if end_date:
        mask &= df["date"] <= pd.to_datetime(end_date)
    if account:
        mask &= df["account"] == account
    subset = df[mask].sort_values("date", ascending=False).head(limit)
    return subset.to_dict("records")


def get_subscriptions_analysis() -> list:
    """Analyze recurring subscriptions: amounts and last transaction dates."""
    df = _load()
    subs = df[df["recurring"] & (df["category"] == "subscriptions")]
    result = []
    for merchant, group in subs.groupby("merchant"):
        last_date = group["date"].max()
        avg_amount = group["amount"].mean()
        months_since = (datetime.now() - last_date).days // 30
        result.append({
            "merchant": merchant,
            "avg_monthly": round(abs(avg_amount), 2),
            "last_transaction": last_date.strftime("%Y-%m-%d"),
            "months_since_last": months_since,
            "possibly_forgotten": months_since >= 3,
        })
    return result


def get_monthly_summary(year: int = None, month: int = None) -> dict:
    """Get income vs expenses summary for a month."""
    df = _load()
    if year and month:
        mask = (df["date"].dt.year == year) & (df["date"].dt.month == month)
    else:
        latest = df["date"].max()
        mask = (df["date"].dt.year == latest.year) & (df["date"].dt.month == latest.month)
    subset = df[mask]
    income = subset[subset["amount"] > 0]["amount"].sum()
    expenses = subset[subset["amount"] < 0]["amount"].sum()
    return {"income": round(income, 2), "expenses": round(abs(expenses), 2),
            "net": round(income + expenses, 2), "year": year, "month": month}


def get_delivery_analysis() -> dict:
    """Analyze delivery orders — late night vs daytime."""
    df = _load()
    delivery = df[df["category"] == "delivery"].copy()
    delivery["hour"] = delivery["date"].dt.hour
    late = delivery[delivery["hour"] >= 21]
    total_amount = abs(delivery["amount"].sum())
    late_amount = abs(late["amount"].sum())
    return {
        "total_monthly_avg": round(total_amount / 12, 2),
        "total_orders": len(delivery),
        "late_night_orders": len(late),
        "late_night_pct": round(len(late) / len(delivery) * 100, 1),
        "late_night_amount": round(late_amount, 2),
    }


def get_weekend_vs_weekday() -> dict:
    """Compare weekend vs weekday spending averages."""
    df = _load()
    expenses = df[df["amount"] < 0].copy()
    expenses["is_weekend"] = expenses["date"].dt.weekday >= 5
    weekend = expenses[expenses["is_weekend"]]
    weekday = expenses[~expenses["is_weekend"]]
    return {
        "weekday_avg_txn": round(abs(weekday["amount"].mean()), 2),
        "weekend_avg_txn": round(abs(weekend["amount"].mean()), 2),
        "weekend_premium_pct": round((abs(weekend["amount"].mean()) / abs(weekday["amount"].mean()) - 1) * 100, 1),
    }


def compare_periods(category: str, period1_start: str, period1_end: str,
                    period2_start: str, period2_end: str) -> dict:
    """Compare spending between two periods."""
    df = _load()
    mask = df["category"] == category if category else df["amount"] < 0

    p1 = df[mask & (df["date"] >= pd.to_datetime(period1_start)) & (df["date"] <= pd.to_datetime(period1_end))]
    p2 = df[mask & (df["date"] >= pd.to_datetime(period2_start)) & (df["date"] <= pd.to_datetime(period2_end))]

    t1, t2 = abs(p1["amount"].sum()), abs(p2["amount"].sum())
    return {
        "period1_total": round(t1, 2),
        "period2_total": round(t2, 2),
        "difference": round(t2 - t1, 2),
        "change_pct": round((t2 - t1) / t1 * 100, 1) if t1 > 0 else 0,
    }


# Tool registry for agents
TOOLS = {
    "get_spending_by_category": get_spending_by_category,
    "get_top_categories": get_top_categories,
    "get_transactions": get_transactions,
    "get_subscriptions_analysis": get_subscriptions_analysis,
    "get_monthly_summary": get_monthly_summary,
    "get_delivery_analysis": get_delivery_analysis,
    "get_weekend_vs_weekday": get_weekend_vs_weekday,
    "compare_periods": compare_periods,
}

TOOL_DESCRIPTIONS = {
    "get_spending_by_category": "Get total spending for a specific category with optional date range. Params: category(str), start_date(str, optional), end_date(str, optional)",
    "get_top_categories": "Get top N spending categories. Params: start_date(str, optional), end_date(str, optional), n(int, default=5)",
    "get_transactions": "Get filtered transaction list. Params: category(str, optional), merchant(str, optional), start_date(str, optional), end_date(str, optional), account(str, optional), limit(int, default=20)",
    "get_subscriptions_analysis": "Analyze all recurring subscriptions — amounts, last dates, forgotten ones. No params.",
    "get_monthly_summary": "Get income vs expenses for a month. Params: year(int, optional), month(int, optional)",
    "get_delivery_analysis": "Analyze delivery orders — late night percentage, amounts. No params.",
    "get_weekend_vs_weekday": "Compare average transaction amounts on weekends vs weekdays. No params.",
    "compare_periods": "Compare spending between two time periods. Params: category(str), period1_start(str), period1_end(str), period2_start(str), period2_end(str)",
}

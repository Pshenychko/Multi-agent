"""Generate synthetic transaction data for Personal Finance Coach."""
import csv, random
from datetime import datetime, timedelta

random.seed(42)

# Parameters
START_DATE = datetime(2024, 12, 1)
END_DATE = datetime(2025, 11, 30)
SALARY = 4500
OUTPUT = "data/transactions.csv"

MERCHANTS = {
    "coffee": ["Aroma Kava", "Lviv Croissants", "Starbucks", "Blue Bottle"],
    "groceries": ["Silpo", "ATB", "Novus", "Costco"],
    "restaurants": ["Puzata Hata", "Murakami", "Pizza Celentano", "Sushi Master"],
    "delivery": ["Glovo", "Bolt Food", "Uber Eats"],
    "transport": ["Bolt", "Uber", "Uklon", "Metro Pass"],
    "entertainment": ["Netflix", "Spotify", "YouTube Premium", "Cinema City"],
    "shopping": ["Zara", "H&M", "Amazon", "Rozetka"],
    "health": ["Pharmacy", "Sportlife", "Doctor Visit"],
    "subscriptions": ["Netflix", "Spotify", "YouTube Premium", "Sportlife", "iCloud", "ChatGPT Plus"],
    "utilities": ["Kyivstar", "Electric Bill", "Water Bill", "Internet"],
    "credit_payment": ["Credit Card Payment"],
    "travel": ["Booking.com", "AliExpress", "Wizz Air"],
}

CATEGORY_MONTHLY = {
    "coffee": (80, 95, 18, 25),
    "groceries": (300, 400, 8, 12),
    "restaurants": (120, 180, 4, 7),
    "delivery": (150, 200, 10, 15),
    "transport": (60, 90, 10, 15),
    "entertainment": (40, 60, 3, 5),
    "shopping": (100, 250, 2, 5),
    "health": (30, 60, 1, 3),
    "subscriptions": (45, 50, 4, 6),
    "utilities": (80, 120, 4, 4),
}


def random_time(date, category):
    if category == "coffee":
        hour = random.choice(range(7, 10))
    elif category == "delivery":
        hour = random.choice(range(11, 23))
        if random.random() < 0.5:
            hour = random.choice(range(21, 24))
    else:
        hour = random.randint(8, 22)
    minute = random.randint(0, 59)
    return date.replace(hour=hour, minute=minute)


def generate():
    rows = []
    current = START_DATE
    while current <= END_DATE:
        month_start = current.replace(day=1)
        days_in_month = 28 if current.month == 2 else 30 if current.month in (4, 6, 9, 11) else 31

        # Salary on 1st and 15th
        for d in [1, 15]:
            sal_date = month_start.replace(day=d, hour=10, minute=0)
            rows.append({
                "date": sal_date.isoformat(),
                "merchant": "Employer Inc",
                "amount": SALARY / 2,
                "currency": "USD",
                "category": "salary",
                "account": "main_debit",
                "recurring": True,
            })

        # Credit card payment
        pay_day = month_start.replace(day=random.randint(25, 28))
        month_idx = (current.year - 2024) * 12 + current.month
        if month_idx % 3 == 0:
            cc_amount = random.uniform(800, 1200)
        else:
            cc_amount = 50
        rows.append({
            "date": pay_day.replace(hour=9).isoformat(),
            "merchant": "Credit Card Payment",
            "amount": -cc_amount,
            "currency": "USD",
            "category": "credit_payment",
            "account": "main_debit",
            "recurring": True,
        })

        # Regular categories
        for cat, (min_total, max_total, min_txn, max_txn) in CATEGORY_MONTHLY.items():
            n_txns = random.randint(min_txn, max_txn)
            total = random.uniform(min_total, max_total)
            amounts = []
            for i in range(n_txns):
                if i == n_txns - 1:
                    amounts.append(round(total - sum(amounts), 2))
                else:
                    amounts.append(round(random.uniform(total / n_txns * 0.5, total / n_txns * 1.5), 2))

            merchants = MERCHANTS.get(cat, ["Unknown"])
            for amt in amounts:
                day = random.randint(1, days_in_month)
                txn_date = month_start.replace(day=day)
                is_weekend = txn_date.weekday() >= 5
                if is_weekend:
                    amt = round(amt * random.uniform(1.3, 1.7), 2)
                txn_date = random_time(txn_date, cat)
                account = "credit_card" if cat in ("shopping", "travel", "entertainment") and random.random() < 0.4 else "main_debit"
                recurring = cat == "subscriptions"
                rows.append({
                    "date": txn_date.isoformat(),
                    "merchant": random.choice(merchants),
                    "amount": -abs(amt),
                    "currency": "USD",
                    "category": cat,
                    "account": account,
                    "recurring": recurring,
                })

        # Sportlife subscription stops after July 2025
        if current.month <= 7 or current.year < 2025:
            pass  # already included in subscriptions
        # Remove sportlife after July
        # (handled by filtering later)

        # Suspicious foreign transactions in December 2024
        if current.month == 12 and current.year == 2024:
            rows.append({
                "date": datetime(2024, 12, 3, 14, 22).isoformat(),
                "merchant": "Booking.com",
                "amount": -890,
                "currency": "USD",
                "category": "travel",
                "account": "credit_card",
                "recurring": False,
            })
            rows.append({
                "date": datetime(2024, 12, 5, 3, 15).isoformat(),
                "merchant": "AliExpress",
                "amount": -234.50,
                "currency": "USD",
                "category": "shopping",
                "account": "credit_card",
                "recurring": False,
            })

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # Post-process: remove Sportlife after July 2025
    final = []
    for r in rows:
        d = datetime.fromisoformat(r["date"])
        if r["merchant"] == "Sportlife" and d > datetime(2025, 7, 31):
            continue
        final.append(r)

    final.sort(key=lambda x: x["date"])

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "merchant", "amount", "currency", "category", "account", "recurring"])
        writer.writeheader()
        writer.writerows(final)

    print(f"Generated {len(final)} transactions → {OUTPUT}")


if __name__ == "__main__":
    generate()

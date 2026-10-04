"""Creates synthetic attendance history (ml/attendance.csv): 12 weeks x 4 meals, ending yesterday.
Replace it with real records once enough are collected."""
import random
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd

random.seed(7); np.random.seed(7)
CAP = 400                                    # students who use the mess
BASE = {"breakfast": 0.62, "lunch": 0.85, "snacks": 0.50, "dinner": 0.76}
DOW = [1.03, 1.00, 0.98, 0.97, 0.90, 1.02, 1.05]          # Mon..Sun
DAYS = 84
start = date.today() - timedelta(days=DAYS)
exam_weeks = {3, 8}
holidays = set(random.sample(range(DAYS), 4))

rows = []
for i in range(DAYS):
    d = start + timedelta(days=i)
    exam, hol = int(i // 7 in exam_weeks), int(i in holidays)
    for meal, base in BASE.items():
        v = CAP * base * DOW[d.weekday()] * (1 + 0.0015 * i)
        if meal == "dinner" and d.weekday() == 4: v *= 0.80         # Friday dinner: students go home
        if meal == "breakfast" and d.weekday() >= 5: v *= 0.85      # weekend breakfast is lighter
        if exam: v *= 1.08
        if hol: v *= 0.60
        v *= np.random.normal(1, 0.03)
        rows.append((d.isoformat(), d.weekday(), meal, exam, hol, int(min(max(round(v), 0), CAP))))

df = pd.DataFrame(rows, columns=["date", "day_of_week", "meal", "is_exam_week", "is_holiday", "attendance"])
df.to_csv(Path(__file__).parent / "attendance.csv", index=False)
print(len(df), "rows saved;", df.date.min(), "to", df.date.max())

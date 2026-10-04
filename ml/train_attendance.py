"""Linear Regression for meal attendance: evaluate on the last 14 days, then forecast the next 7 days."""
import json
from datetime import date, timedelta
from pathlib import Path
import joblib, numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).parent
MEALS = ["breakfast", "lunch", "snacks", "dinner"]
df = pd.read_csv(HERE / "attendance.csv", parse_dates=["date"]).sort_values(["meal", "date"])
df["lag_7"] = df.groupby("meal").attendance.shift(7)          # same meal, one week earlier
df = df.dropna().reset_index(drop=True)
FEATS = ["day_of_week", "meal", "is_exam_week", "is_holiday", "lag_7"]

def new_model():
    prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["day_of_week", "meal"])], remainder="passthrough")
    return Pipeline([("prep", prep), ("lr", LinearRegression())])

cut = df.date.max() - pd.Timedelta(days=13)                    # time-based split: last 14 days are the test set
train, test = df[df.date < cut], df[df.date >= cut]
model = new_model().fit(train[FEATS], train.attendance)
pred = model.predict(test[FEATS])

def score(y, p):
    return {"mae": float(mean_absolute_error(y, p)), "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}
meal_avg = test.meal.map(train.groupby("meal").attendance.mean())
metrics = {"Linear Regression": score(test.attendance, pred),
           "Baseline: same as last week": score(test.attendance, test.lag_7),
           "Baseline: meal average": score(test.attendance, meal_avg)}
for k, v in metrics.items():
    print(f"{k:30s} MAE {v['mae']:5.1f} | RMSE {v['rmse']:5.1f} | R2 {v['r2']:.3f}")

# daily totals for the actual vs predicted chart
t = test.assign(pred=pred).groupby("date")[["attendance", "pred"]].sum()
out = {"test": {"labels": [d.strftime("%a %d %b") for d in t.index], "actual": t.attendance.round().astype(int).tolist(),
                "predicted": t.pred.round().astype(int).tolist()}, "metrics": metrics}

# refit on everything, then forecast tomorrow .. +7 days (lag_7 comes from the last 7 known days)
model = new_model().fit(df[FEATS], df.attendance)
last = df.date.max().date()
hist = df.set_index(["meal", "date"]).attendance
fut = [(last + timedelta(days=k), m) for k in range(1, 8) for m in MEALS]
X = pd.DataFrame([{"day_of_week": d.weekday(), "meal": m, "is_exam_week": 0, "is_holiday": 0,
                   "lag_7": hist[(m, pd.Timestamp(d - timedelta(days=7)))]} for d, m in fut])
X["pred"] = np.clip(model.predict(X[FEATS]), 0, None).round().astype(int)
X["day"] = [d for d, _ in fut]
days = sorted(set(X.day))
out["forecast"] = {"labels": [d.strftime("%a %d %b") for d in days],
                   "by_meal": {m.title(): X[X.meal == m].pred.tolist() for m in MEALS},
                   "total": [int(X[X.day == d].pred.sum()) for d in days]}

(HERE / "models").mkdir(exist_ok=True)
joblib.dump(model, HERE / "models" / "attendance_lr.joblib")
(HERE / "models" / "attendance_forecast.json").write_text(json.dumps(out, indent=2))
print("Saved ml/models/attendance_lr.joblib and attendance_forecast.json")

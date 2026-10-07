"""Fills MongoDB with demo attendance, reviews and complaints for the test student (so dashboards have data)."""
import random
from datetime import datetime, timedelta
from app import db, predict_category, MEALS

random.seed(1)
me = "student@college.edu"
for col in (db.attendance, db.reviews, db.complaints):
    col.delete_many({"student": me})
TIMES = {"breakfast": (7, 9), "lunch": (12, 14), "snacks": (17, 18), "dinner": (20, 21)}
for i in range(20, 0, -1):
    day = datetime.now() - timedelta(days=i)
    if day.weekday() == 4 and random.random() < 0.5:
        continue
    for m in MEALS:
        if random.random() < {"breakfast": .6, "lunch": .9, "snacks": .5, "dinner": .8}[m]:
            h = random.randint(*TIMES[m])
            db.attendance.insert_one({"student": me, "date": day.strftime("%Y-%m-%d"), "meal": m, "status": "present", "time": f"{h:02d}:{random.randint(0, 59):02d}"})
for i in range(8):
    r = {k: random.randint(2, 5) for k in ("quality", "temperature", "hygiene", "staff", "speed", "overall")}
    db.reviews.insert_one({"student": me, "meal": random.choice(MEALS), "ratings": r, "comment": "Demo review", "date": datetime.now() - timedelta(days=i * 2)})
texts = ["The rice was undercooked and cold", "Found a hair in the dal", "Waited 40 minutes in the queue", "The server was rude to us",
         "Please add more variety to the menu", "The sambar was too salty"]
for i, t in enumerate(texts):
    db.complaints.insert_one({"cid": f"C-{300 + i}", "student": me, "name": "Chaitali", "meal": random.choice(MEALS), "text": t, "category": predict_category(t),
                              "status": random.choice(["Pending", "Under Review", "Resolved"]), "date": datetime.now() - timedelta(days=i * 3)})
print("Demo data added for", me)

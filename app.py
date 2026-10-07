import os
from collections import Counter
import calendar
import hashlib
import hmac
import time
from datetime import date, datetime, timedelta
from functools import wraps
from bson import ObjectId
from flask import abort, Flask, render_template, request, redirect, session, jsonify, url_for
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")
db = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))["smart_mess"]

NAV = {
 "student": [("dashboard","Dashboard"),("attendance","Attendance"),("reviews","Reviews"),("menu","Weekly Menu"),("nutrition","Nutrition"),("profile","Profile")],
 "admin": [("dashboard","Dashboard"),("approvals","Approvals"),("qr","QR Code"),("crowd","Crowd Analytics"),("waste","Food Waste"),("complaints","Complaints"),("menu","Menu Management")],
}

@app.context_processor
def inject():
    return dict(NAV=NAV, role=session.get("role"), name=session.get("name", ""))

def need(role):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if session.get("role") != role:
                return redirect(url_for("login"))
            return f(*a, **k)
        return w
    return deco

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form["role"]
        u = db.users.find_one({"email": request.form["email"].strip().lower(), "role": role})
        if u and check_password_hash(u["password"], request.form["password"]):
            if u.get("status", "approved") != "approved":
                return render_template("login.html", error="Your account is waiting for admin approval.", role=role)
            session.update(user=u["email"], role=role, name=u.get("name", "there"))
            return redirect(url_for(role, page_name="dashboard"))
        return render_template("login.html", error="Email or password is incorrect.", role=role)
    return render_template("login.html", role=request.args.get("role", "student"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        pw, pw2 = request.form["password"], request.form["confirm"]
        err = None
        if len(pw) < 6:
            err = "Password must be at least 6 characters."
        elif pw != pw2:
            err = "Passwords do not match."
        elif db.users.find_one({"email": email}):
            err = "This email is already registered."
        if err:
            return render_template("signup.html", error=err, name=name, email=email)
        db.users.insert_one({"name": name, "email": email, "password": generate_password_hash(pw),
                             "role": "student", "status": "pending", "created": datetime.now()})
        return render_template("signup.html", done=True)
    return render_template("signup.html")

@app.route("/admin/approvals")
@need("admin")
def approvals():
    users = list(db.users.find({"role": "student", "status": "pending"}).sort("created", -1))
    return render_template("admin_approvals.html", active="approvals", users=users)

@app.post("/admin/approvals/<action>/<email>")
@need("admin")
def approval_action(action, email):
    if action == "approve":
        db.users.update_one({"email": email, "status": "pending"}, {"$set": {"status": "approved"}})
    elif action == "reject":
        db.users.delete_one({"email": email, "status": "pending"})
    return redirect(url_for("approvals"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

def page(role, page):
    if page not in dict(NAV[role]):
        abort(404)
    tpl = f"{role}_{page}.html"
    if not os.path.exists(os.path.join(app.template_folder, tpl)):
        tpl = "soon.html"
    return render_template(tpl, active=page, today=datetime.now().strftime("%A, %d %B %Y"))

@app.route("/student/<page_name>")
@need("student")
def student(page_name):
    return page("student", page_name)

@app.route("/admin/<page_name>")
@need("admin")
def admin(page_name):
    return page("admin", page_name)

MEALS = ["breakfast", "lunch", "snacks", "dinner"]
CRITERIA = [("quality", "Food Quality"), ("temperature", "Food Temperature"), ("hygiene", "Hygiene"),
            ("staff", "Staff Behaviour"), ("speed", "Serving Speed"), ("overall", "Overall Experience")]
STATUSES = ["Pending", "Under Review", "Resolved"]

_model = None
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml", "models")

def predict_category(text):
    """Classify complaint text with the trained SVM. Returns 'Unclassified' until the model is trained."""
    global _model
    path = os.path.join(MODEL_DIR, "complaint_svm.joblib")
    if _model is None:
        if not os.path.exists(path):
            return "Unclassified"
        import joblib
        _model = joblib.load(path)
    return str(_model.predict([text])[0])

def load_metrics():
    import json
    path = os.path.join(MODEL_DIR, "metrics.json")
    return json.load(open(path)) if os.path.exists(path) else None

@app.route("/student/reviews", methods=["GET", "POST"])
@need("student")
def reviews():
    me = session["user"]
    if request.method == "POST":
        meal = request.form.get("meal", "lunch")
        if request.form["kind"] == "review":
            ratings = {k: int(request.form.get(k) or 0) for k, _ in CRITERIA}
            if ratings["overall"] == 0:
                return redirect(url_for("reviews", err=1))
            db.reviews.insert_one({"student": me, "meal": meal, "ratings": ratings,
                                   "comment": request.form.get("comment", "").strip(), "date": datetime.now()})
            return redirect(url_for("reviews", sent="review"))
        text = request.form["text"].strip()
        if text:
            n = db.complaints.count_documents({}) + 1
            db.complaints.insert_one({"cid": f"C-{200 + n}", "student": me, "name": session.get("name", ""), "meal": meal,
                                      "text": text, "category": predict_category(text), "status": "Pending", "date": datetime.now()})
        return redirect(url_for("reviews", sent="complaint"))
    return render_template("student_reviews.html", active="reviews", meals=MEALS, criteria=CRITERIA,
                           my_reviews=list(db.reviews.find({"student": me}).sort("date", -1).limit(8)),
                           my_complaints=list(db.complaints.find({"student": me}).sort("date", -1).limit(8)))

@app.route("/admin/complaints")
@need("admin")
def complaints():
    items = list(db.complaints.find().sort("date", -1))
    overall = [r["ratings"]["overall"] for r in db.reviews.find() if r["ratings"].get("overall")]
    return render_template("admin_complaints.html", active="complaints", items=items[:10], total=len(items),
                           resolved=sum(c["status"] == "Resolved" for c in items),
                           pending=sum(c["status"] == "Pending" for c in items),
                           avg=round(sum(overall) / len(overall), 1) if overall else "–",
                           cats=dict(Counter(c["category"] for c in items)),
                           meals=dict(Counter(c["meal"].title() for c in items)), statuses=STATUSES, metrics=load_metrics())

@app.post("/admin/complaints/<cid>/status")
@need("admin")
def complaint_status(cid):
    status = request.form.get("status")
    if status in STATUSES:
        db.complaints.update_one({"cid": cid}, {"$set": {"status": status}})
    return redirect(url_for("complaints"))

def load_forecast():
    import json
    path = os.path.join(MODEL_DIR, "attendance_forecast.json")
    return json.load(open(path)) if os.path.exists(path) else None

@app.route("/admin/dashboard")
@need("admin")
def admin_dashboard():
    day = datetime.now().strftime("%Y-%m-%d")
    today_rows = list(db.attendance.find({"date": day}))
    overall = [r["ratings"]["overall"] for r in db.reviews.find() if r["ratings"].get("overall")]
    return render_template("admin_dashboard.html", active="dashboard", today=datetime.now().strftime("%A, %d %B %Y"),
                           meals=MEALS, counts=Counter(a["meal"] for a in today_rows),
                           present=len({a["student"] for a in today_rows}),
                           pending=db.complaints.count_documents({"status": "Pending"}),
                           rating=round(sum(overall) / len(overall), 1) if overall else "–", forecast=load_forecast())

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TIMES = {"breakfast": "7:30 – 9:00 AM", "lunch": "12:30 – 2:00 PM", "snacks": "5:00 – 6:00 PM", "dinner": "8:00 – 9:30 PM"}
SEED_MENU = {"breakfast": [("Idli", 65, 2, 12), ("Sambar", 80, 4, 10), ("Chai", 45, 1, 8)],
             "lunch": [("Rice", 206, 4, 45), ("Dal Tadka", 180, 11, 24), ("Aloo Sabzi", 150, 3, 28)],
             "snacks": [("Samosa", 140, 4, 18), ("Chai", 45, 1, 8)],
             "dinner": [("Chapati", 70, 2.5, 14), ("Paneer Masala", 265, 14, 8), ("Dal Makhani", 210, 10, 30)]}

def get_menu():
    """Weekly menu from MongoDB; creates a starter menu the first time."""
    if db.menu.count_documents({}) == 0:
        db.menu.insert_many([{"day": d, "meals": {m: [dict(name=n, kcal=k, protein=p, carbs=c) for n, k, p, c in items]
                              for m, items in SEED_MENU.items()}} for d in DAYS])
    return {d["day"]: d["meals"] for d in db.menu.find()}

def current_meal():
    h = datetime.now().hour
    return "breakfast" if h < 10 else "lunch" if h < 15 else "snacks" if h < 19 else "dinner"

def student_stats(email):
    rows = list(db.attendance.find({"student": email}))
    today = date.today()
    dates = sorted({date.fromisoformat(r["date"]) for r in rows})
    out = dict(rows=rows, dates=set(dates), present=0, absent=0, pct=0, streak=0, best=0, span=0, peak="–", meal="–", absent_day="–")
    if not dates:
        return out
    span = min(30, (today - dates[0]).days + 1)
    window = {d for d in dates if (today - d).days < span}
    d, streak = (today if today in window else today - timedelta(days=1)), 0
    while d in out["dates"]:
        streak, d = streak + 1, d - timedelta(days=1)
    best = run = 0; prev = None
    for d in dates:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best, prev = max(best, run), d
    hours = Counter(r["time"][:2] for r in rows if r.get("time")).most_common(1)
    missed = Counter((today - timedelta(days=i)).strftime("%A") for i in range(span) if (today - timedelta(days=i)) not in window)
    out.update(present=len(window), absent=span - len(window), pct=round(100 * len(window) / span, 1), streak=streak, best=best, span=span,
               meal=Counter(r["meal"] for r in rows).most_common(1)[0][0].title(),
               peak=datetime.strptime(hours[0][0], "%H").strftime("%I:00 %p").lstrip("0") if hours else "–",
               absent_day=missed.most_common(1)[0][0] if missed else "–")
    return out

@app.route("/student/dashboard")
@need("student")
def student_dashboard():
    me, st, today = session["user"], student_stats(session["user"]), date.today()
    week = [today - timedelta(days=i) for i in range(6, -1, -1)]
    per_day = Counter(r["date"] for r in st["rows"])
    overall = [r["ratings"]["overall"] for r in db.reviews.find({"student": me}) if r["ratings"].get("overall")]
    return render_template("student_dashboard.html", active="dashboard", today=datetime.now().strftime("%A, %d %B %Y"), meals=MEALS,
        times=MEAL_TIMES, menu_today=get_menu()[DAYS[today.weekday()]], st=st, now_meal=current_meal(),
        chart={"labels": [d.strftime("%a") for d in week], "values": [per_day.get(d.isoformat(), 0) for d in week]},
        today_count=per_day.get(today.isoformat(), 0), rating=round(sum(overall) / len(overall), 1) if overall else "–",
        n_complaints=db.complaints.count_documents({"student": me}))

@app.route("/student/attendance")
@need("student")
def student_attendance():
    st, today = student_stats(session["user"]), date.today()
    weeks = []
    for w in calendar.monthcalendar(today.year, today.month):
        row = []
        for n in w:
            d = date(today.year, today.month, n) if n else None
            cls = "e" if not n else "p" if d in st["dates"] else "a" if d < today and st["span"] and (today - d).days < st["span"] else ""
            row.append((n, cls))
        weeks.append(row)
    return render_template("student_attendance.html", active="attendance", st=st, weeks=weeks, month=today.strftime("%B %Y"), meals=MEALS)

@app.route("/student/menu")
@need("student")
def student_menu():
    menu = get_menu()
    return render_template("student_menu.html", active="menu", days=DAYS, menu=menu, meals=MEALS, times=MEAL_TIMES, today_name=DAYS[date.today().weekday()])

@app.route("/student/profile")
@need("student")
def student_profile():
    me, st = session["user"], student_stats(session["user"])
    acts = [(datetime.strptime(f"{r['date']} {r.get('time', '00:00')}", "%Y-%m-%d %H:%M"), "✅", f"Marked attendance for {r['meal'].title()}") for r in st["rows"]]
    acts += [(r["date"], "⭐", f"Rated {r['meal'].title()} — {r['ratings']['overall']} stars") for r in db.reviews.find({"student": me})]
    acts += [(c["date"], "📋", f"Raised complaint: {c['text'][:45]}") for c in db.complaints.find({"student": me})]
    return render_template("student_profile.html", active="profile", st=st, email=me, acts=sorted(acts, key=lambda a: a[0], reverse=True)[:6],
        n_reviews=db.reviews.count_documents({"student": me}), n_complaints=db.complaints.count_documents({"student": me}))

@app.route("/admin/menu")
@need("admin")
def admin_menu():
    day = request.args.get("day", DAYS[date.today().weekday()])
    return render_template("admin_menu.html", active="menu", days=DAYS, day=day if day in DAYS else DAYS[0], menu=get_menu(), meals=MEALS)

def edit_menu(day, meal, fn):
    if day in DAYS and meal in MEALS:
        get_menu()
        items = db.menu.find_one({"day": day})["meals"][meal]
        fn(items)
        db.menu.update_one({"day": day}, {"$set": {f"meals.{meal}": items}})

@app.post("/admin/menu/add")
@need("admin")
def menu_add():
    f = request.form
    num = lambda k: float(f.get(k) or 0)
    if f.get("name", "").strip():
        edit_menu(f["day"], f["meal"], lambda items: items.append(dict(name=f["name"].strip(), kcal=num("kcal"), protein=num("protein"), carbs=num("carbs"))))
    return redirect(url_for("admin_menu", day=f["day"]))

@app.post("/admin/menu/delete")
@need("admin")
def menu_delete():
    f = request.form
    edit_menu(f["day"], f["meal"], lambda items: items.pop(int(f["idx"])) if 0 <= int(f["idx"]) < len(items) else None)
    return redirect(url_for("admin_menu", day=f["day"]))

GOALS = {"kcal": 2200, "protein": 60, "carbs": 280}
UNITS = {"kcal": "kcal", "protein": "g protein", "carbs": "g carbs"}

@app.route("/student/nutrition")
@need("student")
def student_nutrition():
    me, today = session["user"], date.today()
    menu_today = get_menu()[DAYS[today.weekday()]]
    logs = list(db.nutrition.find({"student": me, "date": today.isoformat()}))
    tot = {k: round(sum(l[k] for l in logs), 1) for k in GOALS}
    pct = {k: min(100, round(100 * tot[k] / GOALS[k])) for k in GOALS}
    by_day = Counter()
    for l in db.nutrition.find({"student": me}):
        by_day[l["date"]] += l["kcal"]
    week = [today - timedelta(days=i) for i in range(6, -1, -1)]
    eaten = {l["item"] for l in logs}
    options = [(m, i) for m in MEALS for i in menu_today[m] if i["name"] not in eaten]
    if not logs:
        tip = "Add what you ate today to see your progress and a suggestion."
    elif min(pct.values()) >= 100:
        tip = "You've reached all of today's targets."
    else:
        low = min(GOALS, key=lambda k: pct[k])
        best = sorted(options, key=lambda o: o[1][low], reverse=True)[:3]
        tip = f"You're at {pct[low]}% of your {'calorie' if low == 'kcal' else low} target. Options still on today's menu: " + \
              ", ".join(f"{i['name']} ({m}, {i[low]:g} {UNITS[low]})" for m, i in best)
    return render_template("student_nutrition.html", active="nutrition", goals=GOALS, tot=tot, pct=pct, logs=logs, tip=tip, meals=MEALS,
                           menu_json={m: [i["name"] for i in menu_today[m]] for m in MEALS},
                           week={"labels": [d.strftime("%a") for d in week], "values": [round(by_day.get(d.isoformat(), 0)) for d in week]})

@app.post("/student/nutrition/add")
@need("student")
def nutrition_add():
    f, today = request.form, date.today()
    item = next((i for i in get_menu()[DAYS[today.weekday()]].get(f.get("meal"), []) if i["name"] == f.get("item")), None)
    try:
        qty = min(max(float(f.get("qty", 1)), .5), 5)
    except ValueError:
        qty = 1
    if item:
        db.nutrition.insert_one({"student": session["user"], "date": today.isoformat(), "meal": f["meal"], "item": item["name"], "qty": qty,
                                 "kcal": item["kcal"] * qty, "protein": item["protein"] * qty, "carbs": item["carbs"] * qty})
    return redirect(url_for("student_nutrition"))

@app.post("/student/nutrition/delete")
@need("student")
def nutrition_delete():
    try:
        db.nutrition.delete_one({"_id": ObjectId(request.form["id"]), "student": session["user"]})
    except Exception:
        pass
    return redirect(url_for("student_nutrition"))

@app.route("/admin/waste")
@need("admin")
def admin_waste():
    logs = list(db.waste.find().sort("date", -1))
    prep, left = sum(l["prepared"] for l in logs), sum(l["leftover"] for l in logs)
    day, meal = {}, {}
    for l in logs:
        for d, k in ((day, l["date"]), (meal, l["meal"])):
            a = d.setdefault(k, [0, 0]); a[0] += l["prepared"]; a[1] += l["leftover"]
    pct = lambda a: round(100 * a[1] / a[0], 1) if a[0] else 0
    by_meal = {m: pct(meal.get(m, [0, 0])) for m in MEALS}
    dates = sorted(day)[-14:]
    alerts = [f"{m.title()}: {v}% of prepared food was left over. Try preparing about {round(v)}% less, or check portion sizes." for m, v in by_meal.items() if v > 10]
    return render_template("admin_waste.html", active="waste", meals=MEALS, logs=logs[:12], alerts=alerts, forecast=load_forecast(), today_iso=date.today().isoformat(),
                           stats=dict(prep=prep, consumed=prep - left, pct=pct([prep, left])),
                           chart={"trend": {"labels": [d[5:] for d in dates], "values": [pct(day[d]) for d in dates]}, "split": [prep - left, left],
                                  "meal": {"labels": [m.title() for m in MEALS], "values": [by_meal[m] for m in MEALS]}})

@app.post("/admin/waste/add")
@need("admin")
def waste_add():
    f = request.form
    try:
        prepared, leftover, d = int(f["prepared"]), int(f["leftover"]), date.fromisoformat(f["date"])
    except (KeyError, ValueError):
        return redirect(url_for("admin_waste"))
    if f.get("meal") in MEALS and prepared > 0 and 0 <= leftover <= prepared:
        db.waste.update_one({"date": d.isoformat(), "meal": f["meal"]}, {"$set": {"prepared": prepared, "leftover": leftover}}, upsert=True)
    return redirect(url_for("admin_waste"))

@app.post("/admin/waste/delete")
@need("admin")
def waste_delete():
    db.waste.delete_one({"date": request.form.get("date"), "meal": request.form.get("meal")})
    return redirect(url_for("admin_waste"))

def mess_code(offset=0):
    """Rotating mess code: changes every 5 minutes, derived from the secret key (HMAC)."""
    slot = int(time.time() // 300) + offset
    return hmac.new(app.secret_key.encode(), str(slot).encode(), hashlib.sha256).hexdigest()[:10].upper()

@app.post("/api/attendance")
@need("student")
def mark_attendance():
    data = request.get_json(silent=True) or {}
    meal, code = data.get("meal"), str(data.get("code", "")).strip().upper()
    if meal not in MEALS:
        return jsonify(ok=False, msg="Choose a valid meal.")
    if code not in (mess_code(0), mess_code(-1)):
        return jsonify(ok=False, msg="Invalid or expired QR code. Scan the code shown at the mess entrance.")
    now = datetime.now()
    day = now.strftime("%Y-%m-%d")
    if db.attendance.find_one({"student": session["user"], "date": day, "meal": meal}):
        return jsonify(ok=False, msg="Already marked for this meal.")
    db.attendance.insert_one({"student": session["user"], "date": day, "meal": meal, "status": "present", "time": now.strftime("%H:%M")})
    return jsonify(ok=True, msg=f"{meal.title()} attendance marked at {now:%H:%M}.")

@app.route("/admin/qr")
@need("admin")
def admin_qr():
    return render_template("admin_qr.html", active="qr")

@app.get("/api/qr-code")
@need("admin")
def qr_code():
    return jsonify(code=mess_code(0), seconds_left=300 - int(time.time() % 300))

def fmt_hour(h):
    return datetime.strptime(str(h), "%H").strftime("%I %p").lstrip("0")

@app.route("/admin/crowd")
@need("admin")
def admin_crowd():
    rows = list(db.attendance.find())
    students = max(db.users.count_documents({"role": "student", "status": "approved"}), 1)
    hours = Counter(int(r["time"][:2]) for r in rows if r.get("time"))
    today = datetime.now().strftime("%Y-%m-%d")
    today_h = Counter(int(r["time"][:2]) for r in rows if r.get("time") and r["date"] == today)
    wd_of = lambda d: date.fromisoformat(d).weekday()
    dates_wd = Counter(wd_of(d) for d in {r["date"] for r in rows})
    per = Counter((r["meal"], wd_of(r["date"])) for r in rows)
    heat = [[min(100, round(100 * per[(m, w)] / dates_wd[w] / students)) if dates_wd[w] else 0 for w in range(7)] for m in MEALS]
    weekly = [round(sum(per[(m, w)] for m in MEALS) / dates_wd[w]) if dates_wd[w] else 0 for w in range(7)]
    info = None
    if hours:
        top = max(hours.values())
        groups = []
        for h in sorted(h for h, c in hours.items() if c >= .75 * top):
            groups.append([h]) if not groups or h != groups[-1][-1] + 1 else groups[-1].append(h)
        bi = max(((i, w) for i in range(4) for w in range(7)), key=lambda t: heat[t[0]][t[1]])
        info = dict(peak=fmt_hour(max(hours, key=hours.get)), least=fmt_hour(min(hours, key=hours.get)),
                    rush=", ".join(f"{fmt_hour(g[0])}–{fmt_hour(g[-1] + 1)}" for g in groups),
                    busiest=f"{MEALS[bi[0]].title()} on {DAYS[bi[1]]} ({heat[bi[0]][bi[1]]}% of students)")
    hrs = list(range(6, 23))
    chart = {"labels": [fmt_hour(h) for h in hrs], "all": [hours.get(h, 0) for h in hrs], "today": [today_h.get(h, 0) for h in hrs],
             "days": [d[:3] for d in DAYS], "weekly": weekly}
    return render_template("admin_crowd.html", active="crowd", info=info, chart=chart, heat=heat, meals=MEALS, days=[d[:3] for d in DAYS], total=len(rows))

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")

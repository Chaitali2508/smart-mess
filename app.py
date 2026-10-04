import os
from collections import Counter
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-me"
db = MongoClient("mongodb://localhost:27017")["smart_mess"]

NAV = {
 "student": [("dashboard","Dashboard"),("attendance","Attendance"),("reviews","Reviews"),("menu","Weekly Menu"),("nutrition","Nutrition"),("profile","Profile")],
 "admin": [("dashboard","Dashboard"),("approvals","Approvals"),("crowd","Crowd Analytics"),("waste","Food Waste"),("complaints","Complaints"),("menu","Menu Management"),("ai","AI Insights")],
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

@app.post("/api/attendance")
@need("student")
def mark_attendance():
    meal, now = request.json.get("meal"), datetime.now()
    day = now.strftime("%Y-%m-%d")
    if db.attendance.find_one({"student": session["user"], "date": day, "meal": meal}):
        return jsonify(ok=False, msg="Already marked for this meal.")
    db.attendance.insert_one({"student": session["user"], "date": day, "meal": meal, "status": "present", "time": now.strftime("%H:%M")})
    return jsonify(ok=True, msg=f"{meal.title()} attendance marked at {now:%H:%M}.")

if __name__ == "__main__":
    app.run(debug=True)

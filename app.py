import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = "change-me"
db = MongoClient("mongodb://localhost:27017")["smart_mess"]

NAV = {
 "student": [("dashboard","Dashboard"),("attendance","Attendance"),("reviews","Reviews"),("menu","Weekly Menu"),("nutrition","Nutrition"),("profile","Profile")],
 "admin": [("dashboard","Dashboard"),("crowd","Crowd Analytics"),("waste","Food Waste"),("complaints","Complaints"),("menu","Menu Management"),("ai","AI Insights")],
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
        u = db.users.find_one({"email": request.form["email"], "password": request.form["password"], "role": role})  # TODO: hash passwords
        if u:
            session.update(user=u["email"], role=role, name=u.get("name", "there"))
            return redirect(url_for(role, page_name="dashboard"))
        return render_template("login.html", error="Email or password is incorrect.", role=role)
    return render_template("login.html", role=request.args.get("role", "student"))

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

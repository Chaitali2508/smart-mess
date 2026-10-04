# in the kitchen: Smart Mess Feedback and Demand Analytics System

Status: in progress.

Flask + MongoDB web app with student and admin portals (QR attendance, feedback and complaints, analytics dashboards). Machine learning (attendance prediction and complaint classification) is being added.

## Run locally
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python seed.py
    python app.py

Then open http://127.0.0.1:5000. The test users in `seed.py` are for development only.

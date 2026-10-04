from pymongo import MongoClient
from werkzeug.security import generate_password_hash
db = MongoClient("mongodb://localhost:27017")["smart_mess"]
db.users.delete_many({"email": {"$in": ["student@college.edu", "admin@college.edu"]}})
db.users.insert_many([
    {"email": "student@college.edu", "password": generate_password_hash("1234"), "role": "student", "name": "Chaitali", "status": "approved"},
    {"email": "admin@college.edu", "password": generate_password_hash("admin"), "role": "admin", "name": "Admin", "status": "approved"},
])
print("Test users added")

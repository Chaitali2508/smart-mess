from pymongo import MongoClient
db = MongoClient("mongodb://localhost:27017")["smart_mess"]
db.users.delete_many({"email": {"$in": ["student@college.edu", "admin@college.edu"]}})
db.users.insert_many([
    {"email": "student@college.edu", "password": "1234", "role": "student", "name": "Chaitali"},
    {"email": "admin@college.edu", "password": "admin", "role": "admin", "name": "Admin"},
])
print("Test users added")

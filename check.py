from pymongo import MongoClient
db = MongoClient("mongodb://localhost:27017")["smart_mess"]
for u in db.users.find():
    print(u.get("email"), "|", u.get("role"), "|", u.get("status"), "|", str(u.get("password"))[:12])

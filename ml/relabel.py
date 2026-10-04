"""Gives a category to complaints still marked 'Unclassified' in MongoDB."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app import db, predict_category
n = 0
for c in db.complaints.find({"category": "Unclassified"}):
    db.complaints.update_one({"_id": c["_id"]}, {"$set": {"category": predict_category(c["text"])}}); n += 1
print(n, "complaints classified")

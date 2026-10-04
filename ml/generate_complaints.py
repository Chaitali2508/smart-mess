"""Creates a synthetic complaints dataset (ml/complaints.csv) for training.
Replace or extend it with real complaints once you have them."""
import random
from pathlib import Path
import pandas as pd

random.seed(42)
FOODS = ["rice", "dal", "roti", "sabzi", "paneer", "idli", "sambar", "chapati", "curd", "tea", "poha", "samosa"]
MEALS = ["breakfast", "lunch", "snacks", "dinner"]
ISSUES = {
 "Food Quality": ["the {f} was undercooked", "the {f} was stale", "found stones in the {f}", "the {f} was not fresh",
    "the {f} smelled bad and looked spoiled", "the {f} was half raw", "the {f} was cold and hard", "{f} was old and food quality is poor",
    "the {f} was burnt", "the {f} was too oily and heavy"],
 "Taste": ["the {f} was too salty", "the {f} was too spicy", "the {f} was bland with no taste", "the {f} was too sweet",
    "the {f} had no flavour at all", "the {f} tasted bitter", "taste of the {f} was awful", "the {f} was very watery and tasteless",
    "too much salt in the {f}", "the {f} did not taste good today"],
 "Hygiene": ["found a hair in the {f}", "found a fly in the {f}", "the plates were not washed properly", "the dining tables were dirty",
    "saw a cockroach near the serving counter", "the water jug was dirty", "the staff were not wearing gloves while serving",
    "the floor of the mess is filthy", "the spoons were greasy and unclean", "there is a bad smell near the kitchen"],
 "Menu": ["the same {f} is served every day", "we need more variety in {m}", "please add {f} to the menu", "the {m} menu does not match what was displayed",
    "there is no non-veg option", "too many fried items in the menu", "{f} is served too often", "please change the weekly menu",
    "no healthy option for {m}", "the {m} menu is boring and repeated"],
 "Staff Behaviour": ["the server was rude to us", "the staff shouted at students", "the cook refused to serve more {f}", "the staff ignored our request",
    "the serving staff behaved badly", "the mess manager was disrespectful", "the worker argued with us at {m}", "staff gave us less {f} on purpose",
    "the staff were impolite and unhelpful", "the counter staff misbehaved"],
 "Delay / Queue": ["waited 40 minutes in the queue", "{m} was served late", "the line was too long", "only one counter was open",
    "the food ran out before I reached the counter", "the mess opened late for {m}", "serving was very slow", "the queue for {m} never moves",
    "we had to wait too long for {f}", "{m} timing was not followed"],
 "Other": ["the wifi in the mess is not working", "the tv in the dining hall is broken", "there is not enough seating", "the fans are not working",
    "the water cooler is not working", "the music is too loud", "the lights keep flickering", "please add a feedback box",
    "the mess entrance is too crowded with bicycles", "the dining hall is very hot"],
}
PRE = ["", "", "Today ", "Yesterday ", "At {m}, ", "Honestly, ", "Again today, ", "Please note: "]
SUF = ["", ".", ".", " Please look into it.", " This is unacceptable.", " Very disappointing.", " Needs improvement.", "!"]

def make(cat):
    f, m = random.choice(FOODS), random.choice(MEALS)
    s = random.choice(PRE).format(m=m) + random.choice(ISSUES[cat]).format(f=f, m=m)
    s = s[0].upper() + s[1:] if s[0].islower() else s
    if random.random() < 0.10:   # mixed complaint: adds a second issue from another category
        other = random.choice([c for c in ISSUES if c != cat])
        s += " and " + random.choice(ISSUES[other]).format(f=random.choice(FOODS), m=random.choice(MEALS))
    return s + random.choice(SUF)

rows = {(make(c), c) for c in ISSUES for _ in range(160)}
df = pd.DataFrame(sorted(rows), columns=["text", "category"]).sample(frac=1, random_state=42)
df.to_csv(Path(__file__).parent / "complaints.csv", index=False)
print(len(df), "complaints saved"); print(df.category.value_counts().to_string())

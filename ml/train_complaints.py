"""Trains SVM (main), Logistic Regression and Naive Bayes on complaint text and compares them."""
import json
from pathlib import Path
import joblib, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC

HERE = Path(__file__).parent
df = pd.read_csv(HERE / "complaints.csv")
X_tr, X_te, y_tr, y_te = train_test_split(df.text, df.category, test_size=0.2, stratify=df.category, random_state=42)

models = {"SVM": LinearSVC(), "Logistic Regression": LogisticRegression(max_iter=1000), "Naive Bayes": MultinomialNB()}
results, svm = {}, None
for name, clf in models.items():
    pipe = make_pipeline(TfidfVectorizer(ngram_range=(1, 2)), clf)
    cv = cross_val_score(pipe, X_tr, y_tr, cv=5).mean()
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    results[name] = {"accuracy": accuracy_score(y_te, pred), "f1_macro": f1_score(y_te, pred, average="macro"), "cv_accuracy": cv}
    print(f"{name:20s} test acc {results[name]['accuracy']:.3f} | macro F1 {results[name]['f1_macro']:.3f} | 5-fold CV {cv:.3f}")
    if name == "SVM":
        svm = pipe
        print("\nSVM per-category report:\n" + classification_report(y_te, pred))

svm.fit(df.text, df.category)   # final model uses all the data
(HERE / "models").mkdir(exist_ok=True)
joblib.dump(svm, HERE / "models" / "complaint_svm.joblib")
(HERE / "models" / "metrics.json").write_text(json.dumps(results, indent=2))
print("Saved ml/models/complaint_svm.joblib")
for t in ["The food was too salty and cold.", "Found a hair in my dal", "Waited 40 minutes for lunch", "Please add chole bhature to the menu"]:
    print(f"  {t!r} -> {svm.predict([t])[0]}")

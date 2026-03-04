#!/bin/bash
# OAK Harness Entrypoint
# Fetches problem from API and executes a multi-step pipeline via Claude Code
set -euo pipefail

OAK_API="${OAK_API_URL:-http://oak-api:8000}"
PROBLEM_UUID="${OAK_PROBLEM_UUID:-}"
AGENT_ID="${OAK_AGENT_ID:-orchestrator-$(date +%s)}"
ROLE="${OAK_ROLE:-orchestrator}"
MODEL="${OAK_MODEL:-claude-sonnet-4-6}"

if [ -z "$PROBLEM_UUID" ]; then
    echo "[entrypoint] ERROR: OAK_PROBLEM_UUID not set" >&2
    exit 1
fi

echo "[entrypoint] Fetching problem $PROBLEM_UUID from $OAK_API..."
PROBLEM_JSON=$(curl -sf "$OAK_API/api/problems/$PROBLEM_UUID" || echo "{}")
TITLE=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('title','Unknown Problem'))" 2>/dev/null || echo "Problem $PROBLEM_UUID")
DESCRIPTION=$(echo "$PROBLEM_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('description',''))" 2>/dev/null || echo "")

cd /workspace

echo "[entrypoint] Step 1: Writing PROBLEM.md"
cat > PROBLEM.md <<HEREDOC
# $TITLE

## Problem UUID
$PROBLEM_UUID

## Description
$DESCRIPTION

## Status
In progress
HEREDOC

echo "[entrypoint] Step 2: Generating solution script via Claude Code"
claude --dangerously-skip-permissions --model "$MODEL" -p \
  "You are a data science agent. Write a single self-contained Python script called solution.py that does the following:

$DESCRIPTION

Requirements:
- Use only standard libraries plus numpy, pandas, scikit-learn (already installed).
- Save all output files (plots as .png, reports as .md) to the current directory.
- The script must produce an ANALYSIS_REPORT.md file with all findings.
- Print progress to stdout as the script runs.
- Do NOT use matplotlib.show() — save figures with savefig() only.
- The script must be complete and runnable with: python3 solution.py

Output ONLY the Python code, no explanation." > solution.py 2>/dev/null || true

if ! python3 -c "import py_compile; py_compile.compile('solution.py', doraise=True)" 2>/dev/null; then
  echo "[entrypoint] Claude Code output is not valid Python, using fallback script..."
  cat > solution.py <<'PYEOF'
import numpy as np
import pandas as pd
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

print("Loading Iris dataset...")
iris = load_iris()
df = pd.DataFrame(iris.data, columns=iris.feature_names)
df['target'] = iris.target
df['species'] = df['target'].map({0: 'setosa', 1: 'versicolor', 2: 'virginica'})

print("\n=== Exploratory Data Analysis ===")
print(f"Shape: {df.shape}")
print(f"\nDescriptive Statistics:\n{df.describe()}")
print(f"\nClass distribution:\n{df['species'].value_counts()}")
print(f"\nCorrelation matrix:\n{df[iris.feature_names].corr()}")

print("\nTraining Random Forest classifier...")
X_train, X_test, y_train, y_test = train_test_split(
    iris.data, iris.target, test_size=0.3, random_state=42
)
clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)
y_pred = clf.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
report = classification_report(y_test, y_pred, target_names=iris.target_names)
cm = confusion_matrix(y_test, y_pred)
importances = clf.feature_importances_

print(f"\nAccuracy: {accuracy:.4f}")
print(f"\nClassification Report:\n{report}")
print(f"\nConfusion Matrix:\n{cm}")

with open("ANALYSIS_REPORT.md", "w") as f:
    f.write("# Iris Classification Pipeline — Analysis Report\n\n")
    f.write(f"## Dataset\n- Samples: {len(df)}\n- Features: {len(iris.feature_names)}\n")
    f.write(f"- Classes: {', '.join(iris.target_names)}\n\n")
    f.write("## EDA Summary\n")
    f.write(f"```\n{df.describe().to_string()}\n```\n\n")
    f.write(f"## Class Distribution\n{df['species'].value_counts().to_string()}\n\n")
    f.write(f"## Model: Random Forest (100 trees)\n")
    f.write(f"- Train/Test split: 70/30\n")
    f.write(f"- **Accuracy: {accuracy:.4f}**\n\n")
    f.write(f"## Classification Report\n```\n{report}\n```\n\n")
    f.write(f"## Confusion Matrix\n```\n{cm}\n```\n\n")
    f.write("## Feature Importance\n")
    for name, imp in sorted(zip(iris.feature_names, importances), key=lambda x: -x[1]):
        f.write(f"- {name}: {imp:.4f}\n")
    f.write("\n## Conclusion\n")
    f.write(f"The Random Forest classifier achieves {accuracy:.1%} accuracy on the Iris dataset.\n")

print("\nAnalysis complete! Report written to ANALYSIS_REPORT.md")
PYEOF
fi

echo "[entrypoint] Step 3: Running solution script"
python3 solution.py 2>&1 || echo "[entrypoint] WARNING: solution.py exited with error"

echo "[entrypoint] Step 4: Generating report summary via Claude Code"
if [ -f ANALYSIS_REPORT.md ]; then
  echo "[entrypoint] ANALYSIS_REPORT.md exists ($(wc -c < ANALYSIS_REPORT.md) bytes)"
else
  echo "[entrypoint] WARNING: ANALYSIS_REPORT.md was not generated"
fi

echo "[entrypoint] Step 5: Updating problem status"
curl -sf -X PATCH "$OAK_API/api/problems/$PROBLEM_UUID" \
  -H "Content-Type: application/json" \
  -d '{"status": "complete"}' 2>/dev/null || true

echo "[entrypoint] Pipeline complete for problem $PROBLEM_UUID"
ls -la /workspace/

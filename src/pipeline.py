"""Pipeline baseline de churn — Arca Continental / Churn Hunters.

Enfoque 'next-month churn' (alerta temprana, sin leakage):
predecir si un cliente ACTIVO dejará de comprar el PRÓXIMO mes,
usando solo features del historial hasta el mes actual.

Para el test: features de los clientes vivos en ene-2026 (t=24) -> P(churn feb-2026).
"""
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.inspection import permutation_importance

DATA = "/Users/xgael/churn-hunters/data"
OUT = "/Users/xgael/churn-hunters/outputs"
os.makedirs(OUT, exist_ok=True)

tr = pd.read_parquet(f"{DATA}/train.parquet")
te = pd.read_parquet(f"{DATA}/test.parquet")

# Índice temporal entero (202401 -> 0, 202601 -> 24, 202602 -> 25)
ym = lambda s: (s // 100 - 2024) * 12 + (s % 100 - 1)
tr["t"] = ym(tr["calmonth"])
te["t"] = ym(te["calmonth"])
tr = tr.sort_values(["customer_id", "t"]).reset_index(drop=True)

# Mes del evento de churn por cliente; y_next = muere el mes siguiente a esta fila
churn_t = tr.loc[tr.target == 1].set_index("customer_id")["t"]
tr["churn_t"] = tr["customer_id"].map(churn_t)
tr["y_next"] = (tr["churn_t"] == tr["t"] + 1).astype(int)

# ---------------- FEATURE ENGINEERING ----------------
g = tr.groupby("customer_id", sort=False)
FEATS = []


def add(name):
    if name not in FEATS:
        FEATS.append(name)


for col, s in [("num_transacciones", "nt"), ("uni_boxes_sold_m", "ub")]:
    tr[s] = tr[col]; add(s)
    for lag in (1, 2, 3, 6):
        tr[f"{s}_lag{lag}"] = g[col].shift(lag); add(f"{s}_lag{lag}")
    tr[f"{s}_ma3"] = g[col].transform(lambda x: x.rolling(3, min_periods=1).mean()); add(f"{s}_ma3")
    tr[f"{s}_ma6"] = g[col].transform(lambda x: x.rolling(6, min_periods=1).mean()); add(f"{s}_ma6")
    tr[f"{s}_std3"] = g[col].transform(lambda x: x.rolling(3, min_periods=2).std()); add(f"{s}_std3")
    tr[f"{s}_cmax"] = g[col].cummax(); add(f"{s}_cmax")
    tr[f"{s}_vs_ma3"] = tr[col] / (tr[f"{s}_ma3"] + 1e-6); add(f"{s}_vs_ma3")
    tr[f"{s}_pct1"] = (tr[col] - tr[f"{s}_lag1"]) / (tr[f"{s}_lag1"].abs() + 1e-6); add(f"{s}_pct1")
    tr[f"{s}_vs_cmax"] = tr[col] / (tr[f"{s}_cmax"] + 1e-6); add(f"{s}_vs_cmax")

tr["tenure"] = g.cumcount(); add("tenure")
tr["zero_nt"] = (tr["num_transacciones"] == 0).astype(int)
tr["zeros_l3"] = g["zero_nt"].transform(lambda x: x.rolling(3, min_periods=1).sum()); add("zeros_l3")
tr["zeros_l6"] = g["zero_nt"].transform(lambda x: x.rolling(6, min_periods=1).sum()); add("zeros_l6")
tr["drop"] = (tr["ub_pct1"] < -0.10).astype(int)
tr["drops_l3"] = g["drop"].transform(lambda x: x.rolling(3, min_periods=1).sum()); add("drops_l3")
tr["month"] = tr["calmonth"] % 100; add("month")

# ---------------- DATASET ENTRENAMIENTO ----------------
# Puntos válidos: filas activas (target==0) con y_next observable (t<=23 -> t+1<=24)
m = (tr["target"] == 0) & (tr["t"] <= 23)
Xy = tr.loc[m, FEATS + ["y_next", "t"]]

# Split temporal: validación = meses recientes (t 22,23 = nov/dic-2025)
val = Xy["t"].isin([22, 23])
Xtr, ytr = Xy.loc[~val, FEATS], Xy.loc[~val, "y_next"]
Xva, yva = Xy.loc[val, FEATS], Xy.loc[val, "y_next"]
print(f"train rows: {len(Xtr):,} | churn rate: {ytr.mean():.4f}")
print(f"val   rows: {len(Xva):,} | churn rate: {yva.mean():.4f}")

clf = HistGradientBoostingClassifier(
    max_iter=400, learning_rate=0.05, max_leaf_nodes=63,
    l2_regularization=1.0, class_weight="balanced", random_state=42,
    early_stopping=True, validation_fraction=0.1, n_iter_no_change=25)
clf.fit(Xtr, ytr)

pva = clf.predict_proba(Xva)[:, 1]
print("\n=== VALIDACIÓN (nov-dic 2025) ===")
print(f"AUC-ROC : {roc_auc_score(yva, pva):.4f}")
print(f"PR-AUC  : {average_precision_score(yva, pva):.4f}  (prevalencia {yva.mean():.4f})")
# Lift en el top-1% de riesgo (qué tan bien priorizamos retención)
k = max(1, int(0.01 * len(pva)))
top = np.argsort(-pva)[:k]
print(f"Precisión en top-1% riesgo: {yva.values[top].mean():.3f}  (lift x{yva.values[top].mean()/yva.mean():.1f})")

# ---------------- SUBMISSION (churn feb-2026) ----------------
pr = tr.loc[tr["t"] == 24, ["customer_id"] + FEATS].copy()
pr["churn_proba"] = clf.predict_proba(pr[FEATS])[:, 1]
sub = te[["customer_id"]].merge(pr[["customer_id", "churn_proba"]], on="customer_id", how="left")
n_new = sub["churn_proba"].isna().sum()
sub["churn_proba"] = sub["churn_proba"].fillna(ytr.mean())
sub.to_csv(f"{OUT}/submission_baseline.csv", index=False)
print(f"\nsubmission: {OUT}/submission_baseline.csv | filas: {len(sub):,} | nuevos sin historia: {n_new}")
print(f"churn esperado feb-2026 (suma proba): {sub['churn_proba'].sum():.0f} clientes en riesgo")

# ---------------- DRIVERS (causa raíz global) ----------------
samp = Xva.sample(min(20000, len(Xva)), random_state=1)
pi = permutation_importance(clf, samp, yva.loc[samp.index], scoring="roc_auc",
                            n_repeats=3, random_state=1, n_jobs=-1)
imp = pd.Series(pi.importances_mean, index=FEATS).sort_values(ascending=False)
print("\n=== TOP 12 DRIVERS DE CHURN (permutation importance) ===")
print(imp.head(12).to_string())
imp.to_csv(f"{OUT}/feature_importance.csv", header=["importance"])
print("\nOK ✅")

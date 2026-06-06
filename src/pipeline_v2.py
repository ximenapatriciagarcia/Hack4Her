"""Pipeline v2 de churn — Arca Continental / Churn Hunters.

Suma a las features de ventas: COOLERS (nivel + tendencia + pérdida) y
ATRIBUTOS de cliente (territorio, subcanal, tamaño — categóricas nativas).
Enfoque 'next-month churn' (alerta temprana, sin leakage).
"""
import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.inspection import permutation_importance

DATA = "/Users/xgael/churn-hunters/data"
OUT = "/Users/xgael/churn-hunters/outputs"
MODELS = "/Users/xgael/churn-hunters/models"
os.makedirs(OUT, exist_ok=True)
os.makedirs(MODELS, exist_ok=True)

ym = lambda s: (s // 100 - 2024) * 12 + (s % 100 - 1)

tr = pd.read_parquet(f"{DATA}/train.parquet")
te = pd.read_parquet(f"{DATA}/test.parquet")
cli = pd.read_parquet(f"{DATA}/clientes.parquet")
co = pd.read_parquet(f"{DATA}/coolers.parquet")

tr["t"] = ym(tr["calmonth"]); tr = tr.sort_values(["customer_id", "t"]).reset_index(drop=True)
co["t"] = ym(co["calmonth"])
churn_t = tr.loc[tr.target == 1].set_index("customer_id")["t"]
tr["churn_t"] = tr["customer_id"].map(churn_t)
tr["y_next"] = (tr["churn_t"] == tr["t"] + 1).astype(int)

FEATS = []
add = lambda n: FEATS.append(n) if n not in FEATS else None

# ---- Features de VENTAS ----
g = tr.groupby("customer_id", sort=False)
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
tr["zero_nt"] = (tr.num_transacciones == 0).astype(int)
tr["zeros_l3"] = g["zero_nt"].transform(lambda x: x.rolling(3, min_periods=1).sum()); add("zeros_l3")
tr["zeros_l6"] = g["zero_nt"].transform(lambda x: x.rolling(6, min_periods=1).sum()); add("zeros_l6")
tr["drop"] = (tr["ub_pct1"] < -0.10).astype(int)
tr["drops_l3"] = g["drop"].transform(lambda x: x.rolling(3, min_periods=1).sum()); add("drops_l3")
tr["month"] = tr["calmonth"] % 100; add("month")

# ---- Features de COOLERS (merge por customer_id + calmonth) ----
co = co.sort_values(["customer_id", "t"])
gc = co.groupby("customer_id", sort=False)
co["nc_lag1"] = gc["num_coolers"].shift(1)
co["nc_cmax"] = gc["num_coolers"].cummax()
cof = co[["customer_id", "calmonth", "num_coolers", "num_doors", "nc_lag1", "nc_cmax"]]
tr = tr.merge(cof, on=["customer_id", "calmonth"], how="left")
tr["nc_vs_cmax"] = tr["num_coolers"] / (tr["nc_cmax"] + 1e-6)
tr["nc_lost"] = (tr["num_coolers"] < tr["nc_lag1"]).astype(float)
for f in ["num_coolers", "num_doors", "nc_vs_cmax", "nc_lost"]:
    add(f)

# ---- Atributos de CLIENTE (categóricas) ----
cli = cli.copy()
cli["rtm_customer_size_d"] = cli["rtm_customer_size_d"].fillna("Desconocido")
tr = tr.merge(cli, on="customer_id", how="left")
CAT = ["territory_d", "comercial_subchannel_d", "rtm_customer_size_d"]
for c in CAT:
    tr[c] = tr[c].astype("category"); add(c)

# ---- Dataset de entrenamiento (next-month, sin leakage) ----
m = (tr["target"] == 0) & (tr["t"] <= 23)
Xy = tr.loc[m, FEATS + ["y_next", "t"]]
val = Xy["t"].isin([22, 23])
Xtr, ytr = Xy.loc[~val, FEATS], Xy.loc[~val, "y_next"]
Xva, yva = Xy.loc[val, FEATS], Xy.loc[val, "y_next"]
print(f"train {len(Xtr):,} churn {ytr.mean():.4f} | val {len(Xva):,} churn {yva.mean():.4f}")
print(f"features: {len(FEATS)} ({len(CAT)} categóricas)")

cat_mask = [c in CAT for c in FEATS]
clf = HistGradientBoostingClassifier(
    max_iter=500, learning_rate=0.05, max_leaf_nodes=63, l2_regularization=1.0,
    class_weight="balanced", categorical_features=cat_mask, random_state=42,
    early_stopping=True, validation_fraction=0.1, n_iter_no_change=25)
clf.fit(Xtr, ytr)

pva = clf.predict_proba(Xva)[:, 1]
auc, prauc = roc_auc_score(yva, pva), average_precision_score(yva, pva)
k = int(0.01 * len(pva)); top = np.argsort(-pva)[:k]
print("\n=== V2 (ventas + coolers + atributos) ===")
print(f"AUC-ROC : {auc:.4f}   (baseline solo-ventas: 0.9560)")
print(f"PR-AUC  : {prauc:.4f}  (baseline 0.3139)")
print(f"Top-1% precisión: {yva.values[top].mean():.3f}  (lift x{yva.values[top].mean()/yva.mean():.1f})")

# ---- Submission ----
prs = tr.loc[tr["t"] == 24, ["customer_id"] + FEATS].copy()
prs["churn_proba"] = clf.predict_proba(prs[FEATS])[:, 1]
sub = te[["customer_id"]].merge(prs[["customer_id", "churn_proba"]], on="customer_id", how="left")
sub["churn_proba"] = sub["churn_proba"].fillna(ytr.mean())
sub.to_csv(f"{OUT}/submission_v2.csv", index=False)
print(f"\nsubmission_v2.csv | filas {len(sub):,}")

# ---- Drivers ----
samp = Xva.sample(min(20000, len(Xva)), random_state=1)
pi = permutation_importance(clf, samp, yva.loc[samp.index], scoring="roc_auc",
                            n_repeats=3, random_state=1, n_jobs=-1)
imp = pd.Series(pi.importances_mean, index=FEATS).sort_values(ascending=False)
print("\n=== TOP 15 DRIVERS ===")
print(imp.head(15).to_string())
imp.to_csv(f"{OUT}/feature_importance_v2.csv", header=["importance"])

# ---- Guardar modelo para la plataforma ----
joblib.dump(clf, f"{MODELS}/churn_model_v2.joblib")
json.dump({"feats": FEATS, "cat": CAT}, open(f"{MODELS}/feature_spec.json", "w"), ensure_ascii=False, indent=2)
print(f"\nmodelo guardado en {MODELS}/churn_model_v2.joblib ✅")

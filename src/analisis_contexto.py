"""Análisis profundo del churn — base de contexto para el agente Gemini."""
import pandas as pd, numpy as np

DATA = "/Users/xgael/churn-hunters/data"
R = {}

tr = pd.read_parquet(f"{DATA}/train.parquet").sort_values(["customer_id", "calmonth"])
meses = sorted(tr.calmonth.unique())
tmap = {m: i for i, m in enumerate(meses)}
tr["t"] = tr.calmonth.map(tmap)
churn_t = tr.loc[tr.target == 1].groupby("customer_id")["t"].min()
tr["churn_t"] = tr.customer_id.map(churn_t)
tr["y_next"] = (tr["churn_t"] == tr["t"] + 1).astype(int)

g = tr.groupby("customer_id", sort=False)
for col, s in [("num_transacciones", "nt"), ("uni_boxes_sold_m", "ub")]:
    tr[f"{s}_cmax"] = g[col].cummax()
    tr[f"{s}_vs_cmax"] = tr[col] / (tr[f"{s}_cmax"] + 1e-6)
    tr[f"{s}_ma3"] = g[col].transform(lambda x: x.rolling(3, min_periods=1).mean())
    tr[f"{s}_vs_ma3"] = tr[col] / (tr[f"{s}_ma3"] + 1e-6)
tr["zero_nt"] = (tr.num_transacciones == 0).astype(int)
tr["zeros_l6"] = g["zero_nt"].transform(lambda x: x.rolling(6, min_periods=1).sum())
tr["tenure"] = g.cumcount()

co = pd.read_parquet(f"{DATA}/coolers.parquet").sort_values(["customer_id", "calmonth"])
gc = co.groupby("customer_id", sort=False)
co["nc_cmax"] = gc["num_coolers"].cummax()
co["nc_lag1"] = gc["num_coolers"].shift(1)
co["nc_vs_cmax"] = co["num_coolers"] / (co["nc_cmax"] + 1e-6)
co["nc_lost"] = (co["num_coolers"] < co["nc_lag1"]).astype(float)
tr = tr.merge(co[["customer_id", "calmonth", "num_coolers", "nc_vs_cmax", "nc_lost"]],
              on=["customer_id", "calmonth"], how="left")
cli = pd.read_parquet(f"{DATA}/clientes.parquet")
tr = tr.merge(cli, on="customer_id", how="left")

# Población "viva" (igual que el train del modelo)
pop = tr[(tr.target == 0) & (tr.t <= 23)]
ch = pop[pop.y_next == 1]
sa = pop[pop.y_next == 0]
print(f"== MAGNITUD ==")
print(f"Filas-mes vivas: {len(pop):,} | se van el próximo mes: {len(ch):,} ({100*pop.y_next.mean():.2f}%)")
print(f"Clientes únicos: {pop.customer_id.nunique():,}")

print(f"\n== PERFIL: el-que-se-va (mes antes) vs sano ==")
feats = ["uni_boxes_sold_m", "num_transacciones", "ub_vs_cmax", "nt_vs_cmax",
         "ub_vs_ma3", "zeros_l6", "nc_vs_cmax", "nc_lost", "tenure", "num_coolers"]
for f in feats:
    print(f"  {f:18s}  churner={ch[f].mean():8.3f}   sano={sa[f].mean():8.3f}")

print(f"\n== CHURN RATE por TAMAÑO ==")
print((100 * pop.groupby("rtm_customer_size_d")["y_next"].mean()).round(2).sort_values(ascending=False).to_string())
print(f"\n== CHURN RATE por TERRITORIO (top 8 y bottom 3) ==")
ter = (100 * pop.groupby("territory_d")["y_next"].agg(["mean", "count"]))
ter["mean"] = ter["mean"]
ter = ter.sort_values("mean", ascending=False)
print((ter["mean"]).round(2).head(8).to_string())
print("  ... menos fuga:")
print((ter["mean"]).round(2).tail(3).to_string())
print(f"\n== CHURN RATE por CANAL (subchannel, top 6) ==")
print((100 * pop.groupby("comercial_subchannel_d")["y_next"].mean()).round(2).sort_values(ascending=False).head(6).to_string())

print(f"\n== TRAYECTORIA pre-deserción (cajas promedio, normalizado a t-6=100) ==")
# Para churners reales, ver ub en los meses antes de churn_t
ev = tr[tr.churn_t.notna()].copy()
ev["rel"] = ev["t"] - ev["churn_t"]  # 0 = mes en que desertó (cajas=0)
traj = ev[ev.rel.between(-6, 0)].groupby("rel")["uni_boxes_sold_m"].mean()
base = traj.get(-6, np.nan)
for rel in range(-6, 1):
    v = traj.get(rel, np.nan)
    pct = 100 * v / base if base else np.nan
    print(f"  t{rel:+d}: {v:7.2f} cajas  ({pct:5.1f}% de t-6)")

print(f"\n== % de churners que perdieron coolers en su último año ==")
lost_any = ev[ev.rel.between(-12, -1)].groupby("customer_id")["nc_lost"].max()
print(f"  {100*lost_any.mean():.1f}% perdió al menos un enfriador antes de irse")

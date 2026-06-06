"""EDA inicial del dataset de churn (Arca Continental · Churn Hunters)."""
import pandas as pd
import numpy as np

SRC = "/Users/xgael/Desktop/Datos comprimidos - churn hunters"

train = pd.read_csv(f"{SRC}/sales_churn_train.csv")
test = pd.read_csv(f"{SRC}/sales_churn_test.csv")

print("==== SHAPES ====")
print("train:", train.shape, "| test:", test.shape)

print("\n==== DTYPES (train) ====")
print(train.dtypes)

print("\n==== NULOS ====")
print("train:\n", train.isna().sum())
print("test:\n", test.isna().sum())

print("\n==== TARGET ====")
print(train["target"].value_counts(dropna=False))
print("churn rate (fila-mes):", round(train["target"].mean(), 4))

print("\n==== CLIENTES ====")
ctr = train["customer_id"].nunique()
cte = test["customer_id"].nunique()
common = len(set(train["customer_id"].unique()) & set(test["customer_id"].unique()))
print("únicos train:", ctr, "| únicos test:", cte, "| en ambos:", common)

print("\n==== CALMONTH (rango temporal) ====")
print("train:", train["calmonth"].min(), "->", train["calmonth"].max(),
      "| nº meses:", train["calmonth"].nunique())
print("test :", test["calmonth"].min(), "->", test["calmonth"].max(),
      "| nº meses:", test["calmonth"].nunique())
print("meses test:", sorted(test["calmonth"].unique()))

print("\n==== FILAS POR CLIENTE (train) ====")
rpc = train.groupby("customer_id").size()
print("min", rpc.min(), "| p50", int(rpc.median()), "| mean", round(rpc.mean(), 1),
      "| max", rpc.max())

print("\n==== ¿COMO SE DEFINE EL TARGET? (target por cliente) ====")
tpc = train.groupby("customer_id")["target"].agg(["min", "max", "sum", "count"])
print("clientes SIEMPRE 0 :", int((tpc["max"] == 0).sum()))
print("clientes SIEMPRE 1 :", int((tpc["min"] == 1).sum()))
print("clientes MIXTO 0->1:", int(((tpc["min"] == 0) & (tpc["max"] == 1)).sum()))
print("distribución de #meses con target=1 por cliente:")
print(tpc["sum"].value_counts().sort_index().head(15))

print("\n==== TARGET RATE POR MES ====")
g = train.groupby("calmonth")["target"].agg(["mean", "count", "sum"])
print(g)

print("\n==== DESCRIBE FEATURES ====")
print(train[["num_transacciones", "uni_boxes_sold_m"]].describe())
print("\nceros num_transacciones:", int((train["num_transacciones"] == 0).sum()))
print("ceros uni_boxes_sold_m :", int((train["uni_boxes_sold_m"] == 0).sum()))
print("negativos uni_boxes    :", int((train["uni_boxes_sold_m"] < 0).sum()))

# Trayectoria de un cliente que hace churn (para entender el patrón)
print("\n==== TRAYECTORIA DE UN CLIENTE QUE HACE CHURN (target llega a 1) ====")
churned = tpc[(tpc["min"] == 0) & (tpc["max"] == 1)].index
if len(churned):
    cid = churned[0]
    print(train[train["customer_id"] == cid].sort_values("calmonth").to_string(index=False))

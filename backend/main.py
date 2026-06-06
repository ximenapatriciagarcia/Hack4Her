"""Centinela API — backend de la plataforma de retención (Arca / Churn Hunters).

Sirve scores y clientes desde Supabase (Postgres) y el historial detallado
desde Parquet (filtro pushdown, sin cargar 5M filas en memoria).
"""
import os
import json
import pandas as pd
import psycopg
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = "/Users/xgael/churn-hunters"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "outputs")
SETTINGS_FILE = os.path.join(ROOT, "backend", "settings.json")


def _load_env():
    for line in open(os.path.join(ROOT, ".env")):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


_load_env()
DB_URL = os.environ["SUPABASE_DB_URL"]

IMPORTANCE = pd.read_csv(os.path.join(OUT, "feature_importance_v2.csv"))
IMPORTANCE.columns = ["feature", "importance"]

DRIVER_LABELS = {
    "ub": "Cajas vendidas este mes", "nt": "Transacciones este mes",
    "nc_vs_cmax": "Pérdida de enfriadores vs su máximo",
    "nt_vs_cmax": "Caída de actividad vs su pico",
    "comercial_subchannel_d": "Subcanal comercial", "territory_d": "Territorio",
    "nt_vs_ma3": "Caída vs promedio reciente", "rtm_customer_size_d": "Tamaño de la tienda",
    "tenure": "Antigüedad como cliente", "zeros_l6": "Meses sin pedir (últimos 6)",
    "num_doors": "Puertas de enfriador", "num_coolers": "Número de enfriadores",
}

# ---------------- SETTINGS (API keys) ----------------
SETTINGS_KEYS = ["gemini_api_key", "elevenlabs_api_key", "retell_api_key", "elevenlabs_voice_id"]


def load_settings() -> dict:
    base = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "elevenlabs_api_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "retell_api_key": os.environ.get("RETELL_API_KEY", ""),
        "elevenlabs_voice_id": os.environ.get("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9"),
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            base.update({k: v for k, v in json.load(open(SETTINGS_FILE)).items() if v})
        except Exception:
            pass
    return base


def save_settings(d: dict) -> None:
    cur = load_settings()
    cur.update({k: v for k, v in d.items() if v})  # solo sobreescribe lo no vacío
    json.dump(cur, open(SETTINGS_FILE, "w"))


def get_setting(key: str) -> str:
    return load_settings().get(key, "")


def _mask(v: str) -> str:
    if not v:
        return ""
    return (v[:6] + "…" + v[-4:]) if len(v) > 12 else "•••"


app = FastAPI(title="Centinela API", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def db():
    return psycopg.connect(DB_URL, connect_timeout=20)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/stats")
def stats():
    with db() as c, c.cursor() as cur:
        cur.execute("select count(*) from churn_scores")
        total = cur.fetchone()[0]
        cur.execute("select riesgo, count(*) from churn_scores group by riesgo")
        por_riesgo = dict(cur.fetchall())
        cur.execute("select coalesce(sum(churn_proba),0) from churn_scores")
        esperados = float(cur.fetchone()[0])
        cur.execute("select count(*) from retention_actions")
        acciones = cur.fetchone()[0]
    alto = por_riesgo.get("alto", 0)
    return {
        "total_clientes": total, "riesgo_alto": alto,
        "riesgo_medio": por_riesgo.get("medio", 0), "riesgo_bajo": por_riesgo.get("bajo", 0),
        "pct_riesgo_alto": round(100 * alto / total, 1) if total else 0,
        "churn_esperado": round(esperados), "acciones_registradas": acciones,
    }


@app.get("/clients")
def clients(riesgo: str | None = None, territorio: str | None = None,
            q: str | None = None, limit: int = Query(50, le=200), offset: int = 0):
    where, params = [], []
    if riesgo:
        where.append("riesgo = %s"); params.append(riesgo)
    if territorio:
        where.append("territory_d = %s"); params.append(territorio)
    if q:
        where.append("customer_id ilike %s"); params.append(f"%{q}%")
    wsql = ("where " + " and ".join(where)) if where else ""
    sql = f"""select customer_id, churn_proba, riesgo, territory_d,
                     comercial_subchannel_d, rtm_customer_size_d
              from v_clientes_riesgo {wsql} order by churn_proba desc limit %s offset %s"""
    with db() as c, c.cursor() as cur:
        cur.execute(sql, params + [limit, offset])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"clients": rows, "limit": limit, "offset": offset}


@app.get("/client/{cid}")
def client(cid: str):
    with db() as c, c.cursor() as cur:
        cur.execute("""select customer_id, churn_proba, riesgo, territory_d,
                              comercial_subchannel_d, rtm_customer_size_d
                       from v_clientes_riesgo where customer_id=%s""", [cid])
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "cliente no encontrado")
        info = dict(zip([d[0] for d in cur.description], row))
    sales = pd.read_parquet(os.path.join(DATA, "train.parquet"),
                            filters=[("customer_id", "==", cid)]).sort_values("calmonth")
    hist = [{"mes": int(m), "transacciones": int(t), "cajas": round(float(b), 1)}
            for m, t, b in zip(sales.calmonth, sales.num_transacciones, sales.uni_boxes_sold_m)]
    try:
        co = pd.read_parquet(os.path.join(DATA, "coolers.parquet"),
                             filters=[("customer_id", "==", cid)]).sort_values("calmonth")
        coolers = [{"mes": int(m), "coolers": float(n), "puertas": int(d)}
                   for m, n, d in zip(co.calmonth, co.num_coolers, co.num_doors)]
    except Exception:
        coolers = []
    return {"info": info, "historial_ventas": hist, "historial_coolers": coolers}


@app.get("/drivers")
def drivers():
    top = IMPORTANCE.head(12).copy()
    top["label"] = top["feature"].map(lambda f: DRIVER_LABELS.get(f, f))
    return {"drivers_globales": top[["feature", "label", "importance"]].to_dict(orient="records")}


@app.get("/segmentos")
def segmentos():
    out = {}
    with db() as c, c.cursor() as cur:
        for dim in ["rtm_customer_size_d", "comercial_subchannel_d", "territory_d"]:
            cur.execute(f"""select {dim} as k,
                                   round(100.0*avg(churn_proba)::numeric,2) as riesgo_prom,
                                   count(*) as n
                            from v_clientes_riesgo group by {dim} order by riesgo_prom desc""")
            out[dim] = [{"grupo": r[0], "riesgo_prom": float(r[1]), "n": r[2]} for r in cur.fetchall()]
    return out


class Action(BaseModel):
    customer_id: str
    accion: str
    notas: str = ""


@app.post("/actions")
def add_action(a: Action):
    with db() as c, c.cursor() as cur:
        cur.execute("""insert into retention_actions (customer_id, accion, notas)
                       values (%s,%s,%s) returning id""", [a.customer_id, a.accion, a.notas])
        aid = cur.fetchone()[0]
        c.commit()
    return {"ok": True, "id": aid}


# ---------------- SETTINGS endpoints ----------------
@app.get("/settings")
def get_settings():
    s = load_settings()
    return {k: {"set": bool(s.get(k)), "masked": _mask(s.get(k, ""))} for k in SETTINGS_KEYS}


class SettingsIn(BaseModel):
    gemini_api_key: str = ""
    elevenlabs_api_key: str = ""
    retell_api_key: str = ""
    elevenlabs_voice_id: str = ""


@app.post("/settings")
def post_settings(s: SettingsIn):
    save_settings(s.model_dump())
    return {"ok": True}

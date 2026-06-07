"""Centinela API — backend de la plataforma de retención (Arca / Churn Hunters).

Sirve scores y clientes desde Supabase (Postgres) y el historial detallado
desde Parquet (filtro pushdown, sin cargar 5M filas en memoria).
"""
import os
import json
import re
import hashlib
import subprocess
import pandas as pd
import psycopg
from fastapi import FastAPI, Query, HTTPException, Response
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
DB_URL = os.environ.get("SUPABASE_DB_URL", "")

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

# Humanización: nombre de tiendita / dueño / teléfono mock (determinístico por customer_id)
TIENDAS = ["Abarrotes Don Pepe", "Tienda La Esquina", "Mini Súper La Guadalupana", "Abarrotes Lupita",
           "El Surtidor", "La Económica", "Tienda Mi Ranchito", "Abarrotes El Ahorro", "La Pasadita",
           "Tiendita Doña Mary", "Súper Las Palmas", "Abarrotes San Juan", "La Michoacana", "El Trébol",
           "Tienda La Bendición", "Abarrotes 3 Hermanos", "La Central", "Mini Súper El Águila"]
DUENOS = ["Don Pepe", "Doña Lupita", "Don Chuy", "María", "Don Beto", "Doña Carmen", "Don Rafa",
          "Lucía", "Don Toño", "Doña Rosa", "Don Memo", "Sra. Juana"]


def humanize(cid: str):
    h = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
    return TIENDAS[h % len(TIENDAS)], DUENOS[(h // 13) % len(DUENOS)], f"55 {10000000 + (h % 89999999)}"

# ---------------- SETTINGS (API keys) ----------------
SETTINGS_KEYS = ["supabase_url", "supabase_anon_key", "supabase_service_key", "supabase_db_url",
                 "gemini_api_key", "elevenlabs_api_key", "retell_api_key", "elevenlabs_voice_id",
                 "retell_from_number"]


def load_settings() -> dict:
    base = {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_anon_key": os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
        "supabase_service_key": os.environ.get("SUPABASE_SECRET_KEY", ""),
        "supabase_db_url": os.environ.get("SUPABASE_DB_URL", ""),
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "elevenlabs_api_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "retell_api_key": os.environ.get("RETELL_API_KEY", ""),
        "elevenlabs_voice_id": os.environ.get("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9"),
        "retell_from_number": os.environ.get("RETELL_FROM_NUMBER", ""),
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
    return psycopg.connect(get_setting("supabase_db_url") or DB_URL, connect_timeout=20)


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
    for row in rows:
        row["tienda"], row["dueno"], row["telefono"] = humanize(row["customer_id"])
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
    info["tienda"], info["dueno"], info["telefono"] = humanize(cid)
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
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_db_url: str = ""
    gemini_api_key: str = ""
    elevenlabs_api_key: str = ""
    retell_api_key: str = ""
    elevenlabs_voice_id: str = ""
    retell_from_number: str = ""


@app.post("/settings")
def post_settings(s: SettingsIn):
    save_settings(s.model_dump())
    return {"ok": True}


def _http_code(args: list) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=15).stdout.strip()


@app.get("/settings/test/{tech}")
def settings_test(tech: str):
    """Prueba real de conexión por tecnología — devuelve {ok, message}."""
    try:
        if tech == "supabase":
            with db() as c, c.cursor() as cur:
                cur.execute("select count(*) from churn_scores")
                n = cur.fetchone()[0]
            return {"ok": True, "message": f"Conectado · {n:,} clientes en churn_scores"}
        if tech == "gemini":
            k = gemini_key()
            if not k:
                return {"ok": False, "message": "Sin API key de Gemini"}
            code = _http_code(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                               f"https://generativelanguage.googleapis.com/v1beta/models?key={k}"])
            return {"ok": code == "200", "message": "Key válida · modelos accesibles" if code == "200" else f"Key rechazada (HTTP {code})"}
        if tech == "elevenlabs":
            k = elevenlabs_key()
            if not k:
                return {"ok": False, "message": "Sin API key de ElevenLabs"}
            voice = get_setting("elevenlabs_voice_id") or "cgSgspJ2msm6clMCkdW9"
            pf = "/tmp/_el_test.json"
            with open(pf, "w") as f:
                json.dump({"text": ".", "model_id": "eleven_multilingual_v2"}, f)
            code = _http_code(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST",
                               f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                               "-H", f"xi-api-key: {k}", "-H", "Content-Type: application/json", "--data", "@" + pf])
            if code == "200":
                return {"ok": True, "message": "Key válida · TTS operativo"}
            if code == "401":
                return {"ok": False, "message": "Key sin permiso 'text_to_speech' — créala con ese scope en ElevenLabs"}
            return {"ok": False, "message": f"TTS rechazado (HTTP {code})"}
        if tech == "retell":
            k = get_setting("retell_api_key")
            if not k:
                return {"ok": False, "message": "Sin API key de Retell"}
            out = subprocess.run(["curl", "-s", "https://api.retellai.com/list-agents",
                                  "-H", f"Authorization: Bearer {k}"], capture_output=True, text=True, timeout=15).stdout
            try:
                agents = json.loads(out)
            except Exception:
                agents = None
            if not isinstance(agents, list):
                return {"ok": False, "message": "Key rechazada por Retell"}
            aid = get_setting("retell_agent_id")
            agente = "Sofía OK" if any(a.get("agent_id") == aid for a in agents) else "agente no configurado"
            numero = "con número" if get_setting("retell_from_number") else "SIN número saliente"
            return {"ok": True, "message": f"Key válida · {len(agents)} agentes · {agente} · {numero}"}
        return {"ok": False, "message": "Tecnología desconocida"}
    except Exception as e:
        return {"ok": False, "message": str(e)[:120]}


# ---------------- AGENTE IA (Gemini) ----------------
def gemini_key() -> str:
    k = get_setting("gemini_api_key")
    if k:
        return k
    # Fallback: key de respaldo (proyectos Veo/Gemini) para desarrollo
    try:
        txt = open(os.path.expanduser("~/Desktop/Beemotional-LandingPage/generate-sequence.py")).read()
        m = re.search(r"(AQ\.[A-Za-z0-9_\-]+)", txt)
        if m:
            return m.group(1)
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY", "")


def build_context() -> str:
    with db() as c, c.cursor() as cur:
        cur.execute("select count(*), count(*) filter (where riesgo='alto') from churn_scores")
        total, alto = cur.fetchone()
        cur.execute("""select rtm_customer_size_d, round(100*avg(churn_proba)::numeric,1), count(*)
                       from v_clientes_riesgo group by 1 order by 2 desc""")
        seg = cur.fetchall()
        cur.execute("""select customer_id, round((churn_proba*100)::numeric,1), territory_d,
                              comercial_subchannel_d, rtm_customer_size_d
                       from v_clientes_riesgo order by churn_proba desc limit 15""")
        top = cur.fetchall()
    drv = [DRIVER_LABELS.get(f, f) for f in IMPORTANCE.head(8)["feature"].tolist()]
    L = [f"Total de clientes activos: {total}. En riesgo ALTO: {alto}.",
         "Churn promedio por tamaño de tienda: " + "; ".join(f"{s[0]} {s[1]}% (n={s[2]})" for s in seg),
         "Drivers de churn (mayor a menor): " + ", ".join(drv),
         "Top 15 clientes en mayor riesgo (negocio · dueño · prob · territorio · canal · tamaño):"]
    for t in top:
        tienda, dueno, _ = humanize(t[0])
        L.append(f"- {tienda} ({dueno}) · {t[1]}% · {t[2]} · {t[3]} · {t[4]}")
    return "\n".join(L)


class Ask(BaseModel):
    message: str


@app.post("/assistant")
def assistant(a: Ask):
    key = gemini_key()
    if not key:
        return {"reply": "Configura la API key de Gemini en Ajustes para activar el agente."}
    system = (
        "Eres Centinela, el asistente de retención de clientes de Arca Continental "
        "(distribuye refrescos a tienditas de abarrotes). Ayudas al gerente comercial a "
        "entender el churn y a priorizar acciones de retención. Responde SIEMPRE en español, "
        "breve y accionable. Responde en TEXTO PLANO, sin markdown: nada de asteriscos, "
        "almohadillas ni negritas; usa guiones simples para listas. Apóyate solo en los datos "
        "del contexto; si te piden algo fuera de ellos, dilo.\n\nCONTEXTO ACTUAL:\n" + build_context()
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": a.message}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048, "thinkingConfig": {"thinkingBudget": 0}},
    }
    pf = "/tmp/_gemini_body.json"
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    model = "gemini-flash-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "--data", "@" + pf],
            capture_output=True, text=True, timeout=45)
        data = json.loads(r.stdout)
        if "error" in data:
            return {"reply": f"Gemini devolvió un error: {data['error'].get('message', 'desconocido')[:160]}"}
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return {"reply": text or "No pude generar una respuesta completa. Intenta reformular la pregunta."}
    except Exception:
        return {"reply": "No pude generar la respuesta (revisa la API key de Gemini en Ajustes)."}


# ---------------- VOZ (ElevenLabs) ----------------
def elevenlabs_key() -> str:
    k = get_setting("elevenlabs_api_key")
    if k:
        return k
    try:
        for line in open(os.path.expanduser("~/dimos/.env")):
            if line.strip().startswith("ELEVENLABS_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.environ.get("ELEVENLABS_API_KEY", "")


@app.post("/tts")
def tts(a: Ask):
    key = elevenlabs_key()
    if not key:
        raise HTTPException(400, "Falta la API key de ElevenLabs (configúrala en Ajustes)")
    voice = get_setting("elevenlabs_voice_id") or "cgSgspJ2msm6clMCkdW9"
    body = {
        "text": a.message[:900],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.3, "similarity_boost": 0.75},
    }
    pf, out = "/tmp/_tts_body.json", "/tmp/_tts_out.mp3"
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", url, "-H", f"xi-api-key: {key}",
             "-H", "Content-Type: application/json", "-H", "Accept: audio/mpeg",
             "--data", "@" + pf, "-o", out], timeout=45)
    except Exception:
        raise HTTPException(502, "Error llamando a ElevenLabs")
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return Response(content=open(out, "rb").read(), media_type="audio/mpeg")
    raise HTTPException(502, "ElevenLabs no devolvió audio (revisa la API key)")


# ---------------- RETENCIÓN (Retell — llamada web) ----------------
class WebCallReq(BaseModel):
    customer_id: str


@app.post("/retention/webcall")
def retention_webcall(a: WebCallReq):
    key = get_setting("retell_api_key")
    agent_id = get_setting("retell_agent_id")
    if not key or not agent_id:
        raise HTTPException(400, "Falta la API key de Retell o el agente (revisa Ajustes / setup)")
    with db() as c, c.cursor() as cur:
        cur.execute("""select territory_d, rtm_customer_size_d, churn_proba
                       from v_clientes_riesgo where customer_id=%s""", [a.customer_id])
        row = cur.fetchone()
    terr, tam, proba = row if row else ("desconocido", "desconocido", 0)
    tienda, dueno, _ = humanize(a.customer_id)
    diag = diagnostico(a.customer_id).get("diagnostico", "")
    body = {
        "agent_id": agent_id,
        "retell_llm_dynamic_variables": {
            "nombre_negocio": tienda, "dueno": dueno,
            "territorio": str(terr), "tamano": str(tam),
            "probabilidad": str(round(float(proba) * 100)) if proba else "alto",
            "diagnostico": diag or "Cliente en riesgo; pregúntale con tacto qué ha cambiado en su negocio.",
        },
        "metadata": {"customer_id": a.customer_id},
    }
    pf = "/tmp/_webcall.json"
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", "https://api.retellai.com/v2/create-web-call",
         "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json",
         "--data", "@" + pf], capture_output=True, text=True, timeout=30)
    try:
        data = json.loads(r.stdout)
    except Exception:
        raise HTTPException(502, "Retell no respondió")
    if "access_token" not in data:
        raise HTTPException(502, f"Retell: {data.get('message', 'sin access_token')}")
    return {"access_token": data["access_token"], "call_id": data.get("call_id"),
            "agent_id": agent_id}


# ---------------- DIAGNÓSTICO PERSONALIZADO (Gemini + CONTEXTO_CHURN.md) ----------------
_CONTEXTO = None


def contexto_churn() -> str:
    global _CONTEXTO
    if _CONTEXTO is None:
        try:
            _CONTEXTO = open(os.path.join(ROOT, "CONTEXTO_CHURN.md"), encoding="utf-8").read()
        except Exception:
            _CONTEXTO = ""
    return _CONTEXTO


def _client_signals(cid: str) -> dict:
    """Señales reales del negocio para que Gemini interprete su situación."""
    with db() as c, c.cursor() as cur:
        cur.execute("""select churn_proba, territory_d, comercial_subchannel_d, rtm_customer_size_d
                       from v_clientes_riesgo where customer_id=%s""", [cid])
        row = cur.fetchone()
    proba, terr, canal, tam = row if row else (0, "?", "?", "?")
    s = pd.read_parquet(os.path.join(DATA, "train.parquet"),
                        filters=[("customer_id", "==", cid)]).sort_values("calmonth")
    cajas = [float(x) for x in s["uni_boxes_sold_m"].tolist()]
    pico = max(cajas) if cajas else 0
    actual = cajas[-1] if cajas else 0
    ceros6 = sum(1 for x in cajas[-6:] if x == 0)
    nc_actual = nc_pico = 0
    try:
        co = pd.read_parquet(os.path.join(DATA, "coolers.parquet"),
                             filters=[("customer_id", "==", cid)]).sort_values("calmonth")
        nc = [float(x) for x in co["num_coolers"].tolist()]
        nc_pico, nc_actual = (max(nc), nc[-1]) if nc else (0, 0)
    except Exception:
        pass
    tienda, dueno, _ = humanize(cid)
    return {
        "negocio": tienda, "dueno": dueno, "territorio": terr, "tamano": tam, "canal": canal,
        "probabilidad_riesgo_pct": round(float(proba) * 100),
        "cajas_mes_actual": round(actual, 1), "cajas_mes_pico": round(pico, 1),
        "pct_de_su_pico": round(100 * actual / pico) if pico else 0,
        "cajas_ultimos_6_meses": [round(x, 1) for x in cajas[-6:]],
        "meses_en_cero_ult6": ceros6,
        "enfriadores_actual": nc_actual, "perdio_enfriador": nc_actual < nc_pico,
    }


@app.post("/retention/diagnostico/{cid}")
def diagnostico(cid: str, refresh: bool = False):
    """Gemini interpreta las señales del cliente + el contexto del churn → explicación personalizada."""
    if not refresh:
        with db() as c, c.cursor() as cur:
            cur.execute("select diagnostico from churn_scores where customer_id=%s", [cid])
            r = cur.fetchone()
        if r and r[0]:
            return {"diagnostico": r[0], "signals": _client_signals(cid), "cached": True}
    key = gemini_key()
    if not key:
        return {"diagnostico": "", "error": "Falta API key de Gemini"}
    sig = _client_signals(cid)
    system = ("Eres analista de retención de Arca Continental. Este es el conocimiento del fenómeno de "
              "deserción de tienditas (úsalo para interpretar):\n\n" + contexto_churn() +
              "\n\nAhora analiza A ESTE negocio en concreto y redacta el diagnóstico siguiendo la instrucción "
              "de la sección 8 (3-5 frases, español de México, sin tecnicismos, con 1-2 acciones).")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": "Datos del negocio:\n" + json.dumps(sig, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 500, "thinkingConfig": {"thinkingBudget": 0}},
    }
    pf = "/tmp/_diag_body.json"
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={key}"
    try:
        r = subprocess.run(["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "--data", "@" + pf],
                           capture_output=True, text=True, timeout=45)
        data = json.loads(r.stdout)
        parts = data["candidates"][0]["content"].get("parts", [])
        texto = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        texto = ""
    if not texto:
        return {"diagnostico": "", "error": "Gemini no generó el diagnóstico", "signals": sig}
    with db() as c, c.cursor() as cur:
        cur.execute("update churn_scores set diagnostico=%s where customer_id=%s", [texto, cid])
        c.commit()
    return {"diagnostico": texto, "signals": sig, "cached": False}


# Registrar la acción de llamada en el log
@app.post("/retention/log")
def retention_log(a: WebCallReq):
    with db() as c, c.cursor() as cur:
        cur.execute("""insert into call_logs (customer_id, resultado)
                       values (%s, %s)""", [a.customer_id, "llamada web iniciada"])
        c.commit()
    return {"ok": True}


@app.get("/retention/result/{call_id}")
def retention_result(call_id: str):
    """Loop de feedback: trae el resultado de la llamada desde Retell y lo guarda en Supabase."""
    key = get_setting("retell_api_key")
    if not key:
        raise HTTPException(400, "Falta la API key de Retell")
    r = subprocess.run(["curl", "-s", f"https://api.retellai.com/v2/get-call/{call_id}",
                        "-H", f"Authorization: Bearer {key}"], capture_output=True, text=True, timeout=20)
    try:
        data = json.loads(r.stdout)
    except Exception:
        raise HTTPException(502, "Retell no respondió")
    an = data.get("call_analysis") or {}
    summary = an.get("call_summary", "")
    sentiment = an.get("user_sentiment", "")
    transcript = data.get("transcript", "")
    status = data.get("call_status", "")
    disc = data.get("disconnection_reason", "") or ""
    dur = int((data.get("duration_ms") or 0) / 1000)
    cid = (data.get("metadata") or {}).get("customer_id", "")
    terminal = status in ("ended", "error")        # estados FINALES de Retell
    ready = terminal or bool(summary)
    if ready:
        if summary or transcript:
            resultado = sentiment or "Completada"
        else:
            resultado = {
                "dial_no_answer": "No contestó", "dial_busy": "Ocupado",
                "dial_failed": "No se pudo marcar", "voicemail_reached": "Buzón de voz",
                "user_not_joined": "No se conectó", "error_user_not_joined": "No se conectó",
                "no_valid_payment": "Pago Retell pendiente",
            }.get(disc, "Sin conversación" if status == "ended" else "Error de llamada")
        with db() as c, c.cursor() as cur:
            cur.execute("""insert into call_logs (call_id, customer_id, guion, resultado, duracion_seg, transcripcion)
                           values (%s,%s,%s,%s,%s,%s)
                           on conflict (call_id) do update set
                             guion = excluded.guion, resultado = excluded.resultado,
                             duracion_seg = excluded.duracion_seg, transcripcion = excluded.transcripcion,
                             customer_id = coalesce(nullif(excluded.customer_id, ''), call_logs.customer_id)""",
                        [call_id, cid, summary, resultado, dur, transcript])
            c.commit()
    return {"ready": ready, "summary": summary, "sentiment": sentiment,
            "status": status, "duration_s": dur, "transcript": transcript[:2000]}


@app.get("/retention/calls")
def retention_calls(limit: int = 20):
    with db() as c, c.cursor() as cur:
        # Auto-cierre: una llamada que lleva >30 min "en curso" ya no se va a resolver
        # (no contestó / se cerró la pestaña). Se marca para que NO se reconsulte en bucle.
        cur.execute("update call_logs set resultado='Sin completar' "
                    "where resultado ilike %s and created_at < now() - interval '30 minutes'",
                    ['llamada en curso%'])
        c.commit()
        cur.execute("""select customer_id, guion, resultado, duracion_seg, created_at, call_id
                       from call_logs order by created_at desc limit %s""", [limit])
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for row in rows:
        if row.get("customer_id"):
            row["tienda"], row["dueno"], _ = humanize(row["customer_id"])
        row["created_at"] = str(row["created_at"])
    return {"calls": rows}


class PhoneCallReq(BaseModel):
    customer_id: str
    to_number: str


@app.post("/retention/phonecall")
def retention_phonecall(a: PhoneCallReq):
    """Llamada telefónica REAL: el agente marca a un número (requiere from_number en Ajustes)."""
    key = get_setting("retell_api_key")
    agent_id = get_setting("retell_agent_id")
    from_number = get_setting("retell_from_number")
    if not key or not agent_id:
        raise HTTPException(400, "Falta la API key o el agente de Retell")
    if not from_number:
        raise HTTPException(400, "Falta el número Retell 'from' — cómpralo/impórtalo y ponlo en Ajustes")
    with db() as c, c.cursor() as cur:
        cur.execute("""select territory_d, rtm_customer_size_d, churn_proba
                       from v_clientes_riesgo where customer_id=%s""", [a.customer_id])
        row = cur.fetchone()
    terr, tam, proba = row if row else ("desconocido", "desconocido", 0)
    tienda, dueno, _ = humanize(a.customer_id)
    diag = diagnostico(a.customer_id).get("diagnostico", "")
    body = {
        "from_number": from_number, "to_number": a.to_number, "override_agent_id": agent_id,
        "retell_llm_dynamic_variables": {
            "nombre_negocio": tienda, "dueno": dueno, "territorio": str(terr), "tamano": str(tam),
            "probabilidad": str(round(float(proba) * 100)) if proba else "alto",
            "diagnostico": diag or "Cliente en riesgo; pregúntale con tacto qué ha cambiado en su negocio.",
        },
        "metadata": {"customer_id": a.customer_id},
    }
    pf = "/tmp/_phonecall.json"
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    r = subprocess.run(["curl", "-s", "-X", "POST", "https://api.retellai.com/v2/create-phone-call",
                        "-H", f"Authorization: Bearer {key}", "-H", "Content-Type: application/json",
                        "--data", "@" + pf], capture_output=True, text=True, timeout=30)
    try:
        data = json.loads(r.stdout)
    except Exception:
        raise HTTPException(502, "Retell no respondió")
    if "call_id" not in data:
        raise HTTPException(502, f"Retell: {data.get('message', 'no se pudo crear la llamada')}")
    with db() as c, c.cursor() as cur:
        cur.execute("""insert into call_logs (call_id, customer_id, resultado)
                       values (%s, %s, %s) on conflict (call_id) do nothing""",
                    [data["call_id"], a.customer_id, "Llamada en curso…"])
        c.commit()
    return {"call_id": data["call_id"], "status": data.get("call_status")}


_TREND = None


@app.get("/trend")
def trend():
    """Tasa de churn (fila-mes) por mes — para la gráfica de tendencia."""
    global _TREND
    if _TREND is None:
        df = pd.read_parquet(os.path.join(DATA, "train.parquet"), columns=["calmonth", "target"])
        g = df.groupby("calmonth")["target"].mean()
        _TREND = [{"mes": int(m), "rate": round(float(r) * 100, 3)} for m, r in g.items()]
    return {"trend": _TREND}

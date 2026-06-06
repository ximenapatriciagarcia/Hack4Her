# Plan de Desarrollo — Plataforma de Retención de Clientes
### Arca Continental · Hackathon "Churn Hunters"

> **Nombre tentativo del producto:** **Centinela** (vigila, anticipa y actúa sobre la deserción)
> **Stack confirmado:** Gemini · ElevenLabs + Retell · Vultr · (sin MongoDB, sin Solana)

---

## 1. Visión

Plataforma que convierte el modelo de churn en **acción**: detecta qué tienditas están por abandonar, **explica por qué**, y **automatiza la retención** (avisos + llamadas de voz con IA) — todo operado con ayuda de un **agente de IA conversacional**.

De *"se nos fue y no supimos por qué"* → a *"estos clientes se van el próximo mes, esta es la causa, y ya los estamos contactando."*

---

## 2. Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND — React + Vite + TS + Tailwind + Sileo (toasts)      │
│  • Dashboard ejecutivo (KPIs, riesgo global, tendencias)      │
│  • Tabla de clientes en riesgo (semáforo, ranking, filtros)   │
│  • Detalle de cliente (trayectoria, "por qué", acción)        │
│  • Agente IA (chat texto+voz) → avisos vía Sileo toasts       │
└───────────────┬──────────────────────────────────────────────┘
                │ REST / WebSocket
┌───────────────▼──────────────────────────────────────────────┐
│ BACKEND — FastAPI (Python)                                    │
│  • /clients /client/{id} /stats   (sirve scores + drivers)    │
│  • Modelo de churn (HistGradientBoosting, joblib)             │
│  • /assistant  → Gemini (asistente + recomendaciones)         │
│  • /retention  → motor de llamadas (Retell + ElevenLabs)      │
│  • Voz: ElevenLabs (voz Jessica/Sara dentro de Retell)        │
└──────┬─────────────────────────────┬──────────────────────────┘
       │                             │
┌──────▼────────────┐       ┌────────▼──────────┐
│ DATOS (local)     │       │ Servicios IA      │
│ Parquet: historial│       │ Gemini (LLM)      │
│   + scores/drivers│       │ ElevenLabs (voz)  │
│ SQLite: acciones  │       │ Retell (llamadas) │
│   + call_logs     │       └───────────────────┘
└───────────────────┘
                  Deploy: VULTR (Docker)
```

> **Sin base de datos externa:** el backend carga los **Parquet** en memoria (historial + scores) y usa **SQLite** (embebido, cero-config) para lo que se escribe en vivo: acciones de retención y registro de llamadas.

---

## 3. Stack y mapeo a premios (sponsors)

| Capa | Tecnología | Premio MLH |
|---|---|---|
| Modelo IA | HistGradientBoosting (sklearn) — **ya entrenado, AUC 0.956** | — |
| Agente / NLG | **Gemini API** | ✅ Best Use of Gemini |
| Voz + llamadas | **ElevenLabs** (voz Sara) dentro de **Retell** (llamadas) | ✅ Best Use of ElevenLabs |
| Hosting/deploy | **Vultr** | ✅ Best Use of Vultr |
| Datos | **Parquet** (lectura) + **SQLite** (escrituras) | — |
| Toasts/avisos | **Sileo** (sileo.aaryan.design) | — (UX) |

**3 premios objetivo: Gemini · ElevenLabs · Vultr.**

---

## 4. Modelo de datos (Parquet + SQLite)

**Lectura (Parquet, generado por el pipeline):**
- **monthly_sales** — historial mensual por cliente (`num_transacciones`, `uni_boxes`).
- **churn_scores** — `customer_id`, `proba`, `riesgo` (alto/medio/bajo), `drivers[]`.

**Escritura (SQLite, en vivo):**
- **retention_actions** — `customer_id`, acción recomendada, estado, responsable, fecha.
- **call_logs** — llamadas Retell: guion, duración, resultado, transcripción.

---

## 5. Módulos de la plataforma

1. **Dashboard ejecutivo** — nº en riesgo, % cartera, revenue en riesgo, tendencia, top drivers globales.
2. **Radar de clientes** — tabla rankeada por probabilidad, semáforo, filtros (segmento, región).
3. **Ficha de cliente** — gráfica de trayectoria de compras, **por qué está en riesgo** (drivers del modelo), acción recomendada (Gemini), botón "Llamar ahora" (Retell+ElevenLabs).
4. **Agente IA "Centinela"** — chat (texto+voz) que: responde "¿quiénes son mis 10 más riesgosos?", explica un cliente, dispara acciones, y **avisa con toasts Sileo** ("⚠️ 3 clientes VIP entraron en riesgo hoy").
5. **Motor de retención automática** — toma los clientes en riesgo → Gemini genera el guion → **Retell ejecuta la llamada con voz ElevenLabs** → registra resultado en SQLite.
6. **Analytics / causa raíz** — drivers globales, segmentos que más desertan, insights redactados por Gemini.

---

## 6. Fases de desarrollo (orden de ejecución)

### Fase 0 — Productizar el modelo *(base)*
- Serializar modelo (`joblib`), script de scoring batch.
- Generar Parquet de `scores + drivers por cliente`.
- *(Opcional)* calibrar probabilidades + SHAP por cliente para el "por qué" individual.

### Fase 1 — Capa de datos local
- Parquet de historial + scores. SQLite con tablas `retention_actions` y `call_logs`.

### Fase 2 — Backend FastAPI
- Endpoints de datos + scoring + stats. Carga Parquet en memoria, SQLite para escrituras. Keys por `.env`.

### Fase 3 — Frontend (Dashboard)
- React + Vite + TS + Tailwind. Recharts para gráficas.
- **Sileo** + adapter `toast.tsx` (reuso del patrón de Forbes ERP).
- Dashboard + Radar + Ficha de cliente.

### Fase 4 — Agente IA (Gemini + voz)
- Backend `/assistant`: Gemini con *tools* que consultan el modelo y los datos.
- Frontend: widget de chat; avisos del agente → **Sileo toasts**.
- Voz: ElevenLabs TTS (voz Sara/Jessica).

### Fase 5 — Retención automática (Retell + ElevenLabs)
- Motor: clientes en riesgo → guion Gemini → **llamada Retell con voz ElevenLabs** → log en SQLite.
- Demo: llamada real a un número de prueba (o simulada en la UI).

### Fase 6 — Deploy en Vultr
- Dockerizar backend + frontend, desplegar, keys en variables de entorno seguras.

### Fase 7 — Pitch & demo
- Recorrido end-to-end + narrativa de impacto ($$ salvado = clientes salvados × ticket).

---

## 7. Decisiones / requisitos pendientes (antes de programar)

1. **Retell:** ¿ya tienes **cuenta + API key de Retell** (y un número telefónico para llamadas)? Es lo único que no tenemos aún. *(Gemini y ElevenLabs ya las tengo.)*
2. **Alcance de la demo:** ¿llamadas **reales** a un número de prueba, o **simuladas** en la UI para el jurado?
3. **Nombre del producto:** ¿"Centinela", u otro?

---

## 8. Riesgos / notas

- **Calibración:** las probabilidades actuales sirven para *ranking* (priorizar), no como conteo absoluto. Calibrar si la métrica del hackathon lo exige.
- **Métrica oficial del hackathon:** aún por confirmar (afecta cómo optimizamos el submission).
- **Clientes nuevos** (sin historia): se manejan con tasa base hasta tener datos.
- **Tiempo:** priorizar Fases 0–4 (dashboard + agente) para tener algo demoable; 5–6 elevan el "wow".

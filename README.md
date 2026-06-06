# Centinela · Retención de clientes para Arca Continental

Plataforma de **predicción y retención de churn** para las tienditas que abastece Arca Continental.
Detecta qué clientes están por abandonar, **explica por qué** y permite **actuar** antes de perderlos.

> Hackathon **Churn Hunters** (MLH).

## Qué hace

- **Modelo de alerta temprana** (next-month churn): predice qué tienditas dejarán de comprar el próximo mes — **AUC 0.966 · lift ×49** en el top-1% de riesgo.
- **Causa raíz**: drivers globales (caída de ventas, pérdida de enfriadores, tamaño/canal/territorio) y por cliente.
- **Dashboard** monocromo (light/dark) con radar de clientes, semáforo de riesgo, ficha con trayectoria y acciones de retención.
- **Agente IA** (Gemini) + voz (ElevenLabs) + llamadas automáticas (Retell) — *en desarrollo*.

## Stack

| Capa | Tech |
|---|---|
| Modelo | scikit-learn (HistGradientBoosting) |
| Backend | FastAPI + psycopg |
| Datos | Supabase (Postgres) + Parquet |
| Frontend | React + Vite + CSS puro + Sileo |
| IA / voz | Gemini · ElevenLabs · Retell |
| Deploy | Vultr |

## Estructura

```
src/         Pipeline de ML (EDA, features, entrenamiento)
backend/     API FastAPI (main.py)
frontend/    Dashboard React (Vite)
models/      Modelo entrenado (.joblib) + spec de features
PLAN.md      Plan de desarrollo
```

## Correr en local

**Datos:** los CSV crudos no se versionan (pesan ~764 MB). Colócalos y genera los Parquet con `src/pipeline_v2.py`.

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn main:app --reload      # :8000

# Frontend
cd frontend && npm install && npm run dev     # :5173
```

Las API keys (Gemini / ElevenLabs / Retell) se configuran desde la pantalla **Ajustes** del dashboard.

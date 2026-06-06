# Pitch · Centinela — Retención de clientes para Arca Continental

> **One-liner:** De *"se nos fue una tiendita y no supimos por qué"* a *"lo predijimos, supimos por qué, y ya lo estamos reteniendo — por teléfono, con IA."*

---

## El problema (HOOK)

Arca Continental surte refrescos a cientos de miles de tienditas. **Pierde clientes y se entera tarde**, cuando ya no compran. No saben *quién* se va a ir ni *por qué*.

> **9,997 tienditas están en riesgo alto AHORA = 201,658 cajas/mes = ~$24 millones MXN/mes en juego.**

## La solución — 3 capas

1. **Predecir** — modelo de alerta temprana: quién deja de comprar el **próximo mes**. AUC 0.966.
2. **Explicar** — causa raíz: se van las **Mini**, que **pierden enfriadores** y bajan pedidos, en ciertos territorios.
3. **Actuar** — agente IA que recomienda y **llama por voz** a la tiendita para retenerla.

---

## Guión de demo (recorrido en vivo)

1. **Dashboard / Radar** — "9,997 en rojo, $24M/mes en juego." Mostrar el semáforo.
2. **Ficha del cliente** — click en el #1 (Mini · Comarca Lagunera · **99.6%**). Mostrar la **trayectoria** cayendo.
3. **Causa raíz** — barras por tamaño: **Mini 38–52% de fuga** vs Gigante <1%. "No es al azar: son las chicas que pierden enfriadores."
4. **Agente Centinela** — preguntarle por voz/chat: *"¿Por qué se van las Mini?"* → responde con datos + **botón ▶ voz**.
5. **Llamada de retención con IA** — en la ficha, click → **hablar en vivo** con el agente (español). "Esto ya está llamando a las tienditas en riesgo."
6. **Cierre / Impacto** — los números de ROI (abajo).

---

## Impacto / ROI (citar de memoria)

- **×49 más eficiente** que actuar al azar: del top-1% que marca el modelo, **44.5% realmente desertan** (vs 0.9% al azar).
- Contactando el riesgo alto y reteniendo solo el 30%: **~540 tienditas salvadas/mes ≈ $1.3M MXN/mes** protegido (recurrente).
- Revenue total en riesgo: **~$24M/mes (~$290M/año)**.

> *Supuestos: $120 MXN/caja y 30% de retención. Ajustar con cifras reales de Arca; el volumen y el lift salen 100% de los datos.*

## Stack & premios

- **Gemini** — agente IA conversacional. 🏆
- **ElevenLabs** — voz del agente (voz "Jessica"). 🏆
- **Retell** — llamada de retención por voz (web call). 🏆
- **Vultr** — deploy (pendiente). 🏆
- Supabase (datos) · React + CSS puro + Sileo (dashboard monocromo light/dark).

## Cierre

> "Centinela convierte un modelo de churn en **acción real**: predice, explica y **retiene por voz** — antes de perder al cliente. Para Arca, son **millones al mes** que hoy se fugan en silencio."

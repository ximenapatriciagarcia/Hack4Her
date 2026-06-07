# Pitch · Centinela — Retención de clientes para Arca Continental

> **One-liner:** De *"se nos fue una tiendita y no supimos por qué"* a *"lo predijimos, supimos por qué, **la llamamos por teléfono con IA** y la retuvimos."*

---

## El problema (HOOK)

Arca Continental surte refrescos a cientos de miles de tienditas. **Pierde clientes y se entera tarde**, cuando ya dejaron de comprar. No saben *quién* se va a ir ni *por qué*.

> **9,997 tienditas en riesgo alto AHORA = ~201,658 cajas/mes ≈ $24 millones MXN/mes en juego.**

## La solución — 3 capas

1. **Predecir** — modelo de alerta temprana: quién deja de comprar el **próximo mes**. **AUC 0.966**, sin leakage (validación temporal).
2. **Explicar** — causa raíz: se van las **Mini**, que **pierden enfriadores** y bajan pedidos, concentradas en ciertos territorios.
3. **Actuar** — agente IA que recomienda y **llama por teléfono de verdad** a la tiendita para retenerla, y **registra el resultado solo**.

---

## 🔥 Prueba viviente (no es teoría — ya pasó)

Llamada **telefónica real** que hizo el agente "Sofía" en vivo, a una tiendita que el modelo marcó al **99.6%**:

> **Sofía →** "Buen día, le llama Sofía de Arca Continental. ¿Hablo con Don Chuy, de **Abarrotes Lupita**?"
> **Don Chuy →** "Las **entregas tardan mucho** en llegar a mi tienda."
> **Sofía →** "Entiendo… ¿le parece que revisemos su frecuencia de entrega? Coordino con su preventista para el **martes**."

- Duración **99 s**, español natural, cierre con siguiente paso concreto.
- **Causa raíz capturada de la boca del cliente** (entregas tardías) — algo que ningún dashboard te da solo.
- Quedó **registrada automáticamente** en el módulo *Llamadas* con transcript y resumen.

→ El loop completo **predecir → explicar → llamar → registrar** ya corre punta a punta.

---

## Guión de demo (recorrido en vivo, ~4 min)

1. **Dashboard / Radar** — "9,997 en rojo, ~$24M/mes en juego." Semáforo + **tendencia de churn** (viene subiendo).
2. **Ficha del cliente** — click en el #1 (Mini · Comarca Lagunera · **99.6%**). Mostrar la **trayectoria de ventas cayendo**.
3. **Causa raíz** — barras por **tamaño** (Mini hasta ~52% de fuga vs Gigante <1%) y por **territorio**. "No es azar: son las chicas que pierden enfriadores."
4. **Agente Centinela** (Gemini) — preguntarle *"¿Por qué se van las Mini?"* → responde con datos, citando **tienditas por su nombre**, con **▶ voz** (ElevenLabs).
5. **Llamada de retención con IA** (Retell) — marcar **en vivo a un teléfono real** → hablar con Sofía en español → al colgar, **aparece sola en *Llamadas*** con resumen.
6. **Ajustes** — focos verde/rojo por tecnología + **"Probar conexión"** real (Supabase, Gemini, Retell en verde). "Es un producto, no un script."
7. **Cierre / Impacto** — los números de ROI.

---

## Impacto / ROI

- **×49 más eficiente** que actuar al azar: del top-1% que marca el modelo, **~44.5% realmente desertan** (vs 0.9% base).
- Contactando el riesgo alto y reteniendo solo el **30%**: **~540 tienditas salvadas/mes ≈ $1.3M MXN/mes** protegido (recurrente).
- Revenue total en riesgo: **~$24M/mes (~$290M/año)**.

> *Supuestos: $120 MXN/caja y 30% de retención. Ajustar con cifras reales de Arca; volumen y lift salen 100% de los datos.*

## Stack & premios

- **Gemini** 🏆 — cerebro del agente IA conversacional (recomendaciones + chat).
- **ElevenLabs** 🏆 — voz del agente (voz "Jessica", español natural).
- **Retell** 🏆 — **llamada telefónica real** de retención (no solo web): el agente marca, conversa y se registra el resultado.
- **Vultr** 🏆 — deploy (pendiente de subir).
- Supabase (datos) · React + CSS puro + Sileo (dashboard monocromo light/dark, awwwards).

## Cierre

> "Centinela convierte un modelo de churn en **acción real**: predice quién se va, explica por qué, **lo llama por teléfono** y registra el resultado — antes de perder al cliente. Para Arca son **millones al mes** que hoy se fugan en silencio. Y no es un mockup: **ya llamó a Don Chuy y supo por qué se iba.**"

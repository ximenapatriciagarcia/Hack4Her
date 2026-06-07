# Contexto del churn — base de conocimiento para el agente Gemini de retención

> **Para qué sirve este documento.** El modelo marca a los negocios que se irán el próximo mes (tabla `churn_scores`, con las features de cada cliente). El **agente Gemini** lee ESTE contexto + los datos del cliente marcado y redacta una explicación **personalizada** ("por qué *este* negocio está en riesgo y qué ofrecerle"). Esa explicación se inyecta en **Retell** para que Sofía hable de los problemas concretos del negocio y la llamada se sienta 100% dedicada.
> Generado del análisis real de **4.79 M filas-mes / 240,366 clientes** (train). No inventar cifras fuera de aquí.

---

## 1. El fenómeno en una frase

**Las tienditas no se van de golpe: se apagan en ~6 meses.** Arca pierde sobre todo a las **chicas (Mini)**, concentradas en el **norte/frontera y Guadalajara**, que dejan de pedir poco a poco hasta llegar a cero. Cuando ya están en cero, es tarde — la oportunidad está **mientras todavía caen**.

## 2. Magnitud

- **0.91 %** de los negocios activos deserta **cada mes** (43,355 eventos en el periodo).
- Parece poco, pero es **fuga recurrente y silenciosa**: nadie se entera hasta que el cliente ya no pide.
- El modelo detecta esto con **AUC 0.966** y un **lift ×49** en el top-1% (de cada 100 que marca como más riesgosos, ~44 realmente desertan, vs <1 al azar).

## 3. 🔑 El patrón universal — el declive de 6 meses (LO MÁS IMPORTANTE)

Cajas compradas, promedio, en los meses **antes** de desertar (normalizado a t-6 = 100 %):

| Mes | t-6 | t-5 | t-4 | t-3 | t-2 | t-1 | t-0 |
|---|---|---|---|---|---|---|---|
| % de su volumen | 100 % | 93 % | 85 % | **75 %** | **58 %** | **25 %** | 0 % |

**Lectura para la llamada:**
- El deterioro empieza **lento** (–7 %, –15 %, –25 %) y se **desploma** en los últimos 2 meses.
- **Ventana de oro = t-3 a t-2** (cuando todavía compra el 50-75 % de lo suyo). Ahí la retención sí salva al cliente.
- Si ya tiene **meses en cero**, está en el borde: la llamada es de rescate urgente.

## 4. Perfil: el que se va (mes antes) vs el sano

| Señal | El que se va | Sano | Lectura |
|---|---|---|---|
| Cajas/mes | **22** | 254 | compra ~**9× menos** |
| Transacciones/mes | **11** | 97 | pide ~**9× menos veces** |
| % de su pico (`ub_vs_cmax`) | **39 %** | 73 % | cayó **61 %** desde su mejor época |
| vs su propio ritmo reciente (`ub_vs_ma3`) | **0.73** | 1.00 | viene **bajando**, no estable |
| Meses en cero (últimos 6) | **0.17** | 0.01 | **13×** más probable que ya haya dejado de pedir algún mes |
| Antigüedad (meses) | 8.2 | 10.9 | el que se va es **más nuevo / menos fidelizado** |
| Enfriadores | 1.25 | 1.56 | tiene **menos** equipo de frío |
| Perdió enfriador (mes) | 2.0 % | 0.8 % | **2.5×** más probable de haber perdido un enfriador |

## 5. Quién se va — segmentos

**Por tamaño (deserción mensual):**
| Mini | Pequeño | Mediano | Grande | Gigante |
|---|---|---|---|---|
| **3.71 %** | 0.64 % | 0.18 % | 0.05 % | 0.03 % |

→ La **Mini deserta ~120× más que la Gigante**. La fuga es casi toda de **tienditas chicas**.

**Por territorio (más fuga):** Monclova 1.42 %, Reynosa 1.38 %, Guadalajara 1.19 %, Matamoros 1.17 %, Saltillo 1.16 %, Laredo 1.16 %, San Luis Potosí 1.09 %, Comarca Lagunera 1.06 %.
**Menos fuga:** Durango 0.30 %, Jalisco 0.57 %, Chihuahua 0.58 %.
→ **Norte/frontera + Guadalajara** son los focos rojos.

**Por canal (subchannel):** **Hogares 1.50 %** (el más alto), luego Tienda orgánica 1.00 %, Verdulería 0.95 %, Farmacia 0.91 %, Panadería 0.87 %, Tortillería 0.86 %.

## 6. Cómo leer a UN cliente (mapa de señales → significado)

Para cada negocio marcado, Gemini recibe sus features. Así se traducen a lenguaje de negocio:

| Señal en los datos | Qué significa para el tendero | Hipótesis de causa |
|---|---|---|
| `ub_vs_cmax` bajo (<0.5) | "Compra mucho menos que en su mejor época" | Perdió ventas: competencia, menos clientela, precio, surtido |
| `ub_vs_ma3` < 1 | "Viene cayendo respecto a su propio ritmo" | Declive **activo** ahora mismo |
| `zeros_l6` ≥ 1 | "Ya tuvo meses sin pedir nada" | Casi en el borde — rescate urgente |
| `nc_lost` = 1 o `nc_vs_cmax` bajo | "Perdió un enfriador" | Menos espacio de frío = menos venta de bebida fría → causa muy accionable |
| `tenure` bajo (<6) | "Cliente nuevo, no fidelizado" | Nunca enganchó del todo |
| Territorio/canal de alto riesgo | Contexto de zona | Problemas logísticos o de mercado de esa plaza |

## 7. De la señal a la oferta (qué debe proponer Sofía)

| Patrón dominante del cliente | Qué ofrecer en la llamada |
|---|---|
| Cae desde su pico pero aún compra (t-3/t-2) | Promo de **reenganche**, revisar **surtido** y mix de producto |
| Perdió enfriador / poco frío | **Revisar o reponer el enfriador** (palanca directa de venta) |
| Meses en cero, al borde | Entender qué pasó (¿cerró? ¿cambió de proveedor? ¿deuda?) y resolver la fricción concreta |
| Quejas de entrega (ej. caso real Don Chuy) | Revisar **frecuencia y horario de entrega**, escalar al preventista |
| Mini nueva en zona de alto riesgo | Acompañamiento cercano del preventista, plan de crecimiento |

## 8. Instrucción para el agente Gemini (cómo redactar la explicación)

> Dado un cliente marcado con sus features, redacta en **3-5 frases, español de México**, claras y SIN tecnicismos:
> 1. **El porqué probable** de su riesgo, leyendo SUS señales (no genérico).
> 2. **1-2 acciones concretas** a ofrecer (de la tabla de §7).
> 3. Un dato humano para que Sofía conecte (su nombre, su zona).
> Reglas: no inventes cifras que no estén en sus datos; no digas "modelo", "churn", "algoritmo" ni "probabilidad"; habla como si conocieras a ESE negocio.

**Ejemplo (cliente real, Abarrotes Lupita / Don Chuy · Comarca Lagunera · Mini · 99.6 %):**
> "Don Chuy trae una caída fuerte: hoy pide cerca de la cuarta parte de lo que pedía en su mejor mes, y el último par de meses bajó rápido. Es una tiendita chica en una zona donde varias están dejando de surtirse. Conviene preguntarle directo qué cambió —suele ser entrega, surtido o el enfriador— y ofrecerle revisar su frecuencia de entrega y una promo para reengancharlo. Hablarle por su nombre y como vecino de la Comarca Lagunera."

## 9. Honestidad / límites (para no sobrevender en el pitch)

- El predictor más fuerte es el **nivel y la caída de compra** (parcialmente tautológico: el que ya casi no compra está por irse). El valor real está en (a) detectarlo **temprano** en la curva de 6 meses y (b) **segmentar** dónde concentrar esfuerzo.
- El **enfriador** es un factor **correlacionado y muy accionable**, pero no es la causa única ni mayoritaria; úsalo como hipótesis, no como afirmación.
- Nombres de tiendita/dueño son **sintéticos** para la demo; en producción salen del CRM real de Arca.

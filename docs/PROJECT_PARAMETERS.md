# LedgerAI — Parámetros del proyecto

**Este archivo es la fuente de verdad del producto.**  
Cualquier sprint, feature o deploy debe alinearse aquí. Se actualiza cuando la empresa prioriza o cambia el alcance.

Agentes / Cursor: regla `.cursor/rules/ledgerai-project-parameters.mdc` (always apply).

---

## 0. Cómo trabajamos (sprints)

### Disparo desde la empresa (protocolo Juan)

Cuando haya cambios pedidos por la empresa, el mensaje típico será:

> **Tarea de la fecha YYYY-MM-DD** (+ contexto de lo que ya llevamos)

El agente debe entonces:

1. **Leer** este documento y el estado actual del repo (no reinventar el producto).  
2. **Generar un sprint** acotado: objetivo, lista priorizada **tarea por tarea** (1 foco activo), DoD *full verificado*.  
3. **Priorizar** calidad profesional sobre cantidad: una capacidad bien cerrada > muchas a medias.  
4. **No** abrir deploy / auth / móvil / Excel / audio a la vez salvo que la tarea lo pida explícitamente.  
5. **Actualizar** la sección 8 (log empresa) y la tabla de orden de sprints si la prioridad cambió.

### Ciclo de sprint

1. **Entrada:** feedback de la empresa vía “tarea de la fecha…”.  
2. **Sprint:** 1 objetivo medible.  
3. **Definition of Done:** *full verificado* (sección 3).  
4. **Salida:** demo corta + checklist + notas de costo si aplica.  
5. **No** abrir frentes nuevos hasta cerrar la tarea activa.

### Orden de sprints (ajustado 2026-08-26 — recomendación contable/arquitectura)

| Orden | Tema | Estado |
|------:|------|--------|
| 0 | Constraint costos: $0 APIs IA; parsers + reglas | **Cerrado (decisión)** |
| 1 | Pipeline E2E: ingerir → leer → clasificar CoA → conciliar → emitir | Objetivo producto |
| 2 | Extracción local PDF/Excel (pdfplumber / openpyxl) | **Hecho** (PDF + CSV/XLSX) |
| 3 | **Cola async + 1 archivo a la vez** (sobrevivir Render Free 512MB / OOM) | **Hecho** |
| 4 | CoA determinista: `account_rules` + limpieza regex + suspense + aprendizaje pasivo | **Hecho** |
| 5 | Controles auditor: cadenazo saldos bancarios; Owner's Draws → Patrimonio | **Hecho** |
| 6 | Reportes SQL (vistas Supabase): Balance cuadre + P&L + Cash flow (`cash_flow_type`) | **Hecho** |
| 7 | Cierre anual: reset P&L → Retained Earnings | **Hecho** |
| 8 | UX cold-start + banner; split-screen extracto/OCR | **Hecho** (banner + split Docs) |
| 9 | Deploy Render free | **Live** (Docker + Tesseract) |
| 10 | Export Excel + tablas TanStack | **Hecho** (openpyxl export + TanStack txs) |
| 11 | Imagen OCR / Audio local | **Hecho** (Tesseract; audio whisper/Groq) |
| 12 | Auth | **Futuro** (fuera de alcance $0 MVP) |

---

## 1. Visión del producto (empresa 2026-08-24)

### Qué debe hacer el agente (pipeline obligatorio)

1. **Tomar** la información (Drive, upload PC/móvil, Excel, PDF, imagen, audio).  
2. **Leer / transcribir** el contenido a datos estructurados.  
3. **Clasificar** cada gasto/ingreso según el **plan de cuentas**.  
4. Cuando los gastos estén clasificados → **conciliar todas las cuentas**.  
5. **Generar reportes** por periodo (mes / año):  
   - Balance general (Balance Sheet)  
   - Estado de pérdidas y ganancias (P&L)  
   - Flujo de efectivo (Cash flow)  
6. **Emitir** los estados financieros de la empresa para cada periodo cerrado.

### Qué no es negociable para la empresa

- **No quieren pagar un “agente IA” comercial / APIs caras como dependencia principal.**  
- Preferencia: **herramientas gratuitas** y **automatizar con código** (parsers, reglas, open source).  
- Es una **web** (navegador, responsive en celular), no una “web app”/PWA obligatoria. Drive es un canal, no el único.

### Nombre del “agente”

Sigue siendo un **agente de bookkeeping cleanup**, pero la inteligencia debe ser **mayormente determinística** (código + reglas + OCR open source). Un LLM de pago solo como **fallback opcional** y documentado en costos — no como requisito para que el producto funcione.

---

## 2. Canales de entrada (multi-herramienta)

| Canal | Origen | Prioridad | Notas |
|-------|--------|-----------|--------|
| Google Drive | Carpetas anidadas | Alta | Ya hay base |
| Subida web (PC) | Drag & drop | Alta | PDF, Excel, img, audio |
| Subida móvil | Cámara / archivos | Alta | Misma API |
| CSV / Excel | Export bancos | Alta | Parser real con openpyxl/pandas (gratis) |
| (Futuro) Email | Facturas | Baja | Después |

---

## 3. Full verificado (Definition of Done)

Una capacidad no está hecha hasta:

- [ ] Flujo feliz documentado  
- [ ] ≥2 casos reales o fixtures  
- [ ] Estados `processing` → `extracted` / `failed` claros  
- [ ] Trazabilidad (origen, tipo, método de extracción: código vs API)  
- [ ] Resultado en sitio correcto (banco → Conciliación; factura → Transacciones; reportes → periodo)  
- [ ] **Sin dependencia obligatoria de API de pago** para el camino feliz (salvo lo que la empresa apruebe por escrito)  

### Checklist formatos

**PDF / Drive** — OK (cola 1-a-1 + pdfplumber).  
**Excel / CSV** — OK (openpyxl/csv → txs).  
**Imagen** — OK (Tesseract eng+spa; Docker).  
**Audio** — OK (faster-whisper opcional / Groq free tier + reglas CoA; sin OpenAI).  
**Reportes** — OK (P&L + Balance + CF O/I/F + vistas SQL + export xlsx).  
**Cold start / RAM** — OK (banner + cola 1-a-1).  
**Auth** — futuro (no bloquea MVP).

---

## 4. Costos — “¿qué gasto y a cuánto?” (constraint empresa)

### 4.0 Política (2026-08-24)

| Principio | Detalle |
|-----------|---------|
| Default | **$0 en APIs de IA** para el flujo principal |
| Permitido gratis | Supabase Free, Vercel Free, Render Free (con sleep), Drive API quota, Groq free tier (opcional) |
| Evitar como dependencia | LlamaParse pago, OpenAI pago, “AI bookkeeping” SaaS |
| Si hace falta pagar | Solo infra mínima (host despierto) y **con aprobación**; registrar en §4.3 |

### 4.1 Recomendación de stack **gratis / código** (Juan → empresa)

| Capacidad hoy (pago) | Reemplazo recomendado (gratis) | Notas |
|----------------------|--------------------------------|--------|
| LlamaParse (PDF tablas) | **pdfplumber** + **pypdf** + parsers de tablas propios | Más trabajo inicial; control total; $0 |
| OpenAI structure (factura) | Regex / plantillas por vendor + reglas de montos/fechas | Fallback LLM **opcional** |
| OpenAI embeddings CoA | Matching por **keywords / aliases** en plan de cuentas; opcional **sentence-transformers** local | Sin API |
| OpenAI Vision (foto) | **Tesseract OCR** (+ preprocess OpenCV si hace falta) | $0, corre en servidor |
| Groq Whisper | **faster-whisper** local, o Groq **free tier** con límite | Preferir local si el host aguanta CPU |
| Hosting | **Render Free** (API+UI un servicio) + Supabase Free | Cold start + 512MB RAM — ver §7 y §11 |
| DB | Supabase Free | Vigilar límites; **agregaciones en SQL/vistas** |

**Honestidad:** OCR bancario “perfecto” con solo pdfplumber es más frágil que LlamaParse; se compensa con **fixtures por banco** (Chase, Wells, etc.) y reglas. Eso es lo que la empresa pide: **automatizar con código**, no alquilar un cerebro.

**Costo real casi inevitable a largo plazo (no es “agente IA”):** electricidad/CPU del servidor, o un VPS barato (~$5–7/mes) si Free se queda corto. Eso no es “pagar OpenAI”.

### 4.2 Infra (referencia)

| Servicio | Free | Pago típico si se aprueba |
|----------|------|---------------------------|
| Vercel | Sí (UI) | Pro ~$20 |
| Render | Sí (sleep) | Starter ~$7–25 |
| Supabase | Sí | Pro ~$25 |

### 4.3 Registro de gasto

| Fecha | Vendor | Plan | USD | Motivo | Aprobado |
|-------|--------|------|-----|--------|----------|
| 2026-08-24 | — | Política $0 IA | 0 | Empresa no quiere pagar agente IA | Empresa |

### 4.4 Planes del producto hacia clientes (TBD empresa)

Sin cambio; el margen no puede depender de APIs caras por documento.

---

## 5. Pipeline funcional objetivo (estados financieros)

```
Ingesta → Transcripción/extracción → Clasificación CoA
    → Conciliación de cuentas → Cierre de periodo
    → Emisión: Balance + P&L + Cash flow (mensual / anual)
```

| Reporte | Estado actual | Objetivo |
|---------|---------------|----------|
| P&L | Parcial (totales + líneas por cuenta en UI) | Por periodo; no mezclar Owner's Draws |
| Balance general | Mínimo / simplificado | Activo = Pasivo + Patrimonio; **inyectar utilidad neta del periodo en Patrimonio** |
| Cash flow | Proxy operativo | Directo desde banco + columna `cash_flow_type` (O/I/F) |
| Emisión por periodo | API + UI básica | Vista SQL + export Excel profesional (después) |
| Cierre anual | No | Reset ingresos/gastos → Retained Earnings |

---

## 6. Producto web (responsive, no “app”)

- Es una **web** en el navegador, no una web-app/PWA obligatoria.  
- **Responsive** en móvil (Documentos, Transacciones, Conciliación, Reportes).  
- Subida desde PC/celular vía navegador; Drive sigue siendo un canal más.  
- Cold start: banner claro “el sistema se está despertando” (Render Free).  
- No priorizar “instalar en el teléfono” hasta que la empresa lo pida.  
- UX avanzada (split-screen PDF, TanStack Table, exceljs): **después** de cola + reglas CoA.

---

## 7. Despliegue en Render (gratis)

**Sí se puede desplegar en Render free**, con matices:

| Tema | Realidad Free |
|------|----------------|
| Un Web Service con `python run.py` (API + `frontend/dist`) | Sí — **live** |
| Bind `0.0.0.0:$PORT` | Obligatorio (ya soportado) |
| RAM | **~512MB** — riesgo OOM si se procesan muchos PDFs en paralelo |
| Disco | **Efímero** — preferir Supabase Storage / DB como fuente de verdad |
| Inactividad | ~15 min → **sleep**; 1.er request lento (cold start) |
| PDFs | **Uno a la vez** vía cola (`document_queue`) — obligatorio para Free |
| DB | **Supabase** (no Postgres de Render) |

**Conclusión:** demos internas OK en Free **solo si** el procesamiento es secuencial + estados en DB. Si no aceptan el “despertar” o necesitan lotes pesados, plan de pago mínimo.

### 7.1 Config Render (repo)

| Archivo | Uso |
|---------|-----|
| `render.yaml` | Blueprint free Web Service `ledgerai` |
| `bin/render-build.sh` | `pip install -e .` + Node 20 + `frontend` build |
| `runtime.txt` | Python 3.11.9 |

**URL live:** `https://ledgerai-6ate.onrender.com`  
**Start:** `python run.py` · **Health:** `GET /health`  
**Repo:** `https://github.com/juanSecuri/bookepping-cleanup-agent` (`main`).

Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`; Drive OAuth opcional.

Env: `EXTRACTION_MODE=local` por defecto.

---

## 8. Feedback de la empresa (log)

| Fecha | Quién / tema | Decisión | Sprint impactado |
|-------|--------------|----------|------------------|
| 2026-08-24 | Juan / revisión | Auditoría + entorno de prueba | Sprint revisión |
| **2026-08-24** | **Empresa (vía Juan)** | **No pagar agente IA: herramientas gratis / automatizar con código.** Pipeline: leer→clasificar CoA→conciliar→Balance/P&L/Cashflow. | **Sprint free-pipeline** |
| 2026-08-24 | Implementación | Default `EXTRACTION_MODE=local`: pdfplumber + reglas CoA; OpenAI/LlamaParse/Groq opcionales (`cloud`). Seed CoA sin embeddings. | free-pipeline T1 |
| 2026-08-24 | Juan / producto | Web responsive (no PWA); deploy Render free + GitHub | **Deploy Render** |
| **2026-08-26** | **Recomendación contable/arquitectura (vía Juan)** | Blindar Render Free (cola 1 archivo); CoA en Supabase (`account_rules`); cadenazo saldos; Owner's Draws; Balance con utilidad en Patrimonio; Cash flow O/I/F; UX cold-start. Split-screen / TanStack / exceljs = backlog. | **Sprint-2026-08-26-render-queue** |
| 2026-08-26 | Implementación | Cola secuencial + cold-start live; luego `account_rules` + Suspense + aprendizaje | **account-rules** |
| 2026-08-26 | Implementación | Cadenazo `statement_periods` + Owner's Draws 3030 + Balance A=P+E + CF O/I/F | **cadenazo-equity** |
| 2026-08-26 | Implementación | Cierre anual → RE 3020 (`fiscal_year_closes`) | **fiscal-year-close** |
| 2026-08-26 | Implementación | `cash_flow_type` + vistas SQL + CSV/XLSX ingest + export xlsx | **sql-views-excel** |
| 2026-08-26 | Implementación | Tesseract+Docker, audio whisper/Groq, split Docs, TanStack txs | **ocr-audio-ux-docker** |

---

## 9. Principios técnicos (siempre)

- Arquitectura limpia; clean code  
- **Código primero, API de pago última opción**  
- Full verificado > feature a medias  
- Un foco por sprint  
- Observabilidad: origen + método de extracción  
- **RAM plana en Free:** nunca procesar lotes pesados en el request HTTP  
- **Agregaciones pesadas en SQL (Supabase)**, no en el proceso Python/JS cuando se pueda  

---

## 10. Arquitectura aceptada (2026-08-26) — resumen ejecutivo

### 10.1 Infra (Render Free)

1. Upload/Drive → fila en cola (`pending`) en Supabase (no OCR síncrono en HTTP).  
2. Worker/loop: **1 documento** → extraer → persistir → liberar memoria → `processed` / `failed`.  
3. UI: estado de carga elegante en cold start (“despertando”).

### 10.2 Clasificación determinista

`texto limpio` → `ILIKE` / keywords en `account_rules` → código CoA.  
Sin match → **Suspense / Gastos no categorizados**; al corregir el usuario → guardar keyword (aprendizaje pasivo).  
Limpieza regex previa (quitar refs de factura, auth codes, fechas ruidosas).

### 10.3 Controles contables

- **Cadenazo:** saldo final mes N = saldo inicial mes N+1 (alerta + pausa si no).  
- **Owner's Draws** → Patrimonio (no P&L).  
- **Cierre anual:** ingresos/gastos → 0; neto a Retained Earnings.  
- **Balance:** Activo = Pasivo + Patrimonio **incluyendo utilidad neta del ejercicio** como línea virtual.  
- **Cash flow:** método directo + `cash_flow_type` (Operating / Investing / Financing).

### 10.4 Backlog UX (cerrado 2026-08-26)

Split-screen extracto/OCR en Documentos | TanStack Table en Transacciones | Export openpyxl (exceljs multipestaña sigue opcional).

---

## 11. Sprint activo (2026-08-26)

**Nombre:** `Sprint-2026-08-26-ocr-audio-ux-docker`  
**Objetivo medible:** Cerrar formatos imagen/audio + UX backlog + deploy Docker con Tesseract.

| # | Tarea | DoD |
|---|--------|-----|
| 1–5 | Cola → … → SQL/Excel | **Hecho** |
| **6 (foco)** | Tesseract + voice local/Groq + split Docs + TanStack + Dockerfile | Upload foto/audio → txs |

**Auth:** permanece **futuro** (no es requisito del MVP $0).

**Ops:** `render.yaml` pasa a `runtime: docker`. Si el servicio ya existía como Python native, sincronizar Blueprint o cambiar runtime en Dashboard a Docker.

---

*LedgerAI — parámetros vivos. Actualizar al cerrar sprints y al hablar con la empresa.*

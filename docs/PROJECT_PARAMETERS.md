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

### Orden de sprints (ajustado 2026-08-24 — empresa)

| Orden | Tema | Estado |
|------:|------|--------|
| 0 | **Constraint costos:** agente “gratis” = parsers/código + free tiers; minimizar APIs de pago | **Activo — decisión de arquitectura** |
| 1 | Pipeline end-to-end: leer → transcribir → clasificar CoA → conciliar → reportes | Objetivo producto (multi-sprint) |
| 2 | Extracción PDF/Excel **sin LlamaParse de pago** (pdfplumber / openpyxl / reglas) | Siguiente implementación |
| 3 | Clasificación CoA por reglas + keywords (+ embeddings locales opcionales) | Pendiente |
| 4 | Conciliación de cuentas (movimientos ↔ txs) full verificado | Parcial |
| 5 | Reportes: **Balance**, **P&L**, **Cash flow** mensual y anual + emitir por periodo | Parcial (solo P&L básico) |
| 6 | Imagen OCR gratis (Tesseract) / Audio local (faster-whisper) | Pendiente |
| 7 | Upload web responsive (PC + celular en navegador; no PWA) | **En curso / deploy** |
| 8 | Auth (si aplica) | Futuro |
| 9 | **Deploy Render free** (API + UI en un Web Service) | **Activo — este sprint** |

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

**PDF / Drive** — base OK; falta camino gratis + regresión.  
**Excel / CSV** — pendiente parser real.  
**Imagen** — pendiente (Tesseract recomendado).  
**Audio** — pendiente (faster-whisper / Groq free tier).  
**Reportes** — P&L parcial; Balance + Cash flow pendientes.

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
| Hosting | Vercel Free (UI) + Render Free / self-host | Cold start OK para interno |
| DB | Supabase Free | Vigilar límites |

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
| P&L | Parcial (totales) | Por periodo, emitible |
| Balance general | No / mínimo | Activo = Pasivo + Patrimonio |
| Cash flow | No | Operativo / inversión / financiamiento; mes y año |
| Emisión por periodo | Cierre básico | PDF/Excel export profesional |

---

## 6. Producto web (responsive, no “app”)

- Es una **web** en el navegador, no una web-app/PWA obligatoria.  
- **Responsive** en móvil (Documentos, Transacciones, Conciliación, Reportes).  
- Subida desde PC/celular vía navegador; Drive sigue siendo un canal más.  
- No priorizar “instalar en el teléfono” hasta que la empresa lo pida.

---

## 7. Despliegue en Render (gratis)

**Sí se puede desplegar en Render free**, con matices:

| Tema | Realidad Free |
|------|----------------|
| Un Web Service con `python run.py` (API + `frontend/dist`) | Sí |
| Bind `0.0.0.0:$PORT` | Obligatorio (ya soportado) |
| Disco | **Efímero** — uploads temporales se pierden al reiniciar |
| Inactividad | ~15 min sin tráfico → **sleep**; 1.er request lento (cold start) |
| PDFs largos | Mejor en background (ya hay patrón) |
| DB | Seguimos con **Supabase** (no hace falta Postgres de Render) |

**Conclusión:** demos internas OK en Free. Si no aceptan el “despertar”, hace falta plan de pago mínimo.

Cuando toque el sprint: build frontend en el build command + `EXTRACTION_MODE=local` + secrets en Dashboard.

Env: no exigir `OPENAI` / `LLAMAPARSE` con camino local activo.

### 7.1 Config Render (repo)

| Archivo | Uso |
|---------|-----|
| `render.yaml` | Blueprint free Web Service `ledgerai` |
| `bin/render-build.sh` | `pip install -e .` + Node 20 + `frontend` build |
| `runtime.txt` | Python 3.11.9 |

**Start:** `python run.py` (respeta `$PORT`, bind `0.0.0.0`).  
**Health:** `GET /health`  
**Repo:** `https://github.com/juanSecuri/bookepping-cleanup-agent` (branch `main`).

Secrets obligatorios en Dashboard / MCP: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.  
Drive opcional: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`.

---

## 8. Feedback de la empresa (log)

| Fecha | Quién / tema | Decisión | Sprint impactado |
|-------|--------------|----------|------------------|
| 2026-08-24 | Juan / revisión | Auditoría + entorno de prueba | Sprint revisión |
| **2026-08-24** | **Empresa (vía Juan)** | **No pagar agente IA: herramientas gratis / automatizar con código.** Pipeline: leer→clasificar CoA→conciliar→Balance/P&L/Cashflow. | **Sprint free-pipeline** |
| 2026-08-24 | Implementación | Default `EXTRACTION_MODE=local`: pdfplumber + reglas CoA; OpenAI/LlamaParse/Groq opcionales (`cloud`). Seed CoA sin embeddings. | free-pipeline T1 |
| 2026-08-24 | Juan / producto | Web responsive (no PWA); deploy Render free + GitHub | **Deploy Render** |

---

## 9. Principios técnicos (siempre)

- Arquitectura limpia; clean code  
- **Código primero, API de pago última opción**  
- Full verificado > feature a medias  
- Un foco por sprint  
- Observabilidad: origen + método de extracción  

---

## 10. Sprint activo sugerido (post 2026-08-24 empresa)

**Nombre:** `Sprint-2026-08-24-free-pipeline`  
**Objetivo medible:** Definir e iniciar el camino de extracción **$0** (sin LlamaParse/OpenAI obligatorios) y mapear gaps de Balance + Cash flow.

**Tarea 1 (foco ahora):** Documento de arquitectura “local extraction” + spike pdfplumber en 1 PDF Chase/Wells real (¿sale tabla usable?).  
**Tarea 2:** Clasificador CoA por reglas (sin embeddings de pago).  
**Tarea 3:** Modelo de reportes Balance + Cash flow (dominio + API stub).  
**Tarea 4:** P&L emitible por periodo (mejorar lo existente).  
**Luego:** Excel parser, Tesseract, whisper local, móvil, deploy.

---

*LedgerAI — parámetros vivos. Actualizar al cerrar sprints y al hablar con la empresa.*

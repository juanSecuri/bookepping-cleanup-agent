# LedgerAI — Parámetros del proyecto

**Este archivo es la fuente de verdad del producto.**  
Cualquier sprint, feature o deploy debe alinearse aquí. Se actualiza cuando la empresa prioriza o cambia el alcance.

Relacionado: roadmap técnico de cloud en las secciones 6–8.  
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

1. **Entrada:** feedback de la empresa (prioridad del mes, clientes, formatos, bancos) vía “tarea de la fecha…”.  
2. **Sprint:** 1 objetivo medible (ej. “Excel extracto → movimientos verificados en UI”).  
3. **Definition of Done:** *full verificado* (sección 3), no “parece que funciona”.  
4. **Salida:** demo corta + checklist marcada en este doc + notas de costo si se tocó un vendor.  
5. **No** abrir frentes nuevos hasta cerrar la tarea activa del sprint.

Orden por defecto (ajustable por la empresa):

| Orden | Tema | Estado |
|------:|------|--------|
| 1 | PDF / Drive anidado + clasificación statement vs factura | En progreso / parcial |
| 2 | Excel / CSV end-to-end | Pendiente validar |
| 3 | Imagen (recibo/factura) | Pendiente validar |
| 4 | Audio | Pendiente validar |
| 5 | Upload web + móvil (PWA / cámara) además de Drive | Pendiente |
| 6 | Auth + multi-usuario | Pendiente |
| 7 | Deploy internet (Vercel UI + API Render/Railway) | Pendiente |
| 8 | P&L / balance / reportes por mes pulidos | Parcial |
| 9 | Planes comerciales del producto (si aplica) | Idea |

---

## 1. Visión (qué es y qué no es)

**Sí:** agente de **bookkeeping cleanup** — poner al día libros atrasados, organizar por mes, clasificar, conciliar, cerrar, generar **P&L** (y luego balance).

**Web app = el producto:** usable desde **PC y celular en el navegador**, no solo “PC con Drive conectado”.

**No:** depender solo de que Google Drive esté linkeado. Drive es *un* canal. La app debe absorber documentos como lo haría un contador en el día a día.

---

## 2. Canales de entrada (multi-herramienta)

Todo debe llegar al mismo pipeline: **ingesta → clasificar → revisar → conciliar → cerrar**.

| Canal | Origen | Prioridad | Notas |
|-------|--------|-----------|--------|
| Google Drive | Carpetas anidadas (banco → cuenta → año) | Alta (ya hay base) | Sync / browse / import |
| Subida web (PC) | Drag & drop / file picker | Alta | PDF, Excel, img, audio |
| Subida móvil (navegador) | Cámara / archivos del teléfono | Alta (web app) | Misma API que PC; UX touch |
| CSV / Excel local | Export bancos / listados | Alta | Parser real, no solo “registrado” |
| (Futuro) Email inbound | Facturas al correo | Baja | Tras canales anteriores |
| (Futuro) API / Zapier | Integraciones | Baja | Cuando haya clientes externos |

**Regla:** si un formato está en el menú, debe estar **verificado** en PC y, cuando exista UI móvil, en viewport móvil. Si no, marcar “experimental” o quitarlo de la UI.

---

## 3. Full verificado (Definition of Done)

Una capacidad no está hecha hasta cumplir:

- [ ] Flujo feliz documentado (pasos + captura o checklist)  
- [ ] Al menos 2 casos reales o fixtures (no solo mock)  
- [ ] Estados visibles: `processing` → `extracted` / `failed` + mensaje útil  
- [ ] Trazabilidad: origen (Drive path / upload / móvil), tipo, APIs usadas  
- [ ] Resultado en el sitio correcto (estado → Conciliación; factura → Transacciones)  
- [ ] Sin quedar colgado en `processing` tras reinicio (reintento o fail claro)  
- [ ] Sin secretos en git; env vars documentadas  

### Checklist por formato

**PDF / Drive**

- [x] Nested folders browse/import (base)  
- [ ] Clasificación estable con path completo  
- [ ] Regresión post-restart  

**Excel / CSV**

- [ ] Upload + Drive  
- [ ] Extracto vs listado  
- [ ] Filas → movimientos/txs  
- [ ] Hojas / encodings  

**Imagen**

- [ ] JPG/PNG upload (PC + móvil)  
- [ ] Vision → vendor, monto, fecha  
- [ ] Casos difíciles  

**Audio**

- [ ] MP3/WAV/M4A  
- [ ] Whisper → estructura  
- [ ] UI + estados  

---

## 4. Costos y planes — “¿qué gasto y a cuánto?”

Estimaciones orientativas en USD (revisar precios oficiales al contratar; cambian).  
Objetivo: saber **qué se paga, por qué, y cuándo subir de plan**.

### 4.1 Infraestructura (para que la web app viva en internet)

| Servicio | Para qué | Free / bajo costo | Plan “fluido” (demo a clientes) | ¿Cuándo pagar? |
|----------|----------|-------------------|----------------------------------|----------------|
| **Vercel** | Frontend SPA | Free suele bastar | Pro ~$20/user/mes si límites | Tráfico / team |
| **Render** (o Railway/Fly) | API FastAPI + workers | Free = duerme (~cold start) | Starter ~$7–25/mes | Demos en vivo, OCR largo |
| **Supabase** | DB + (futuro) Auth/Storage | Free | Pro ~$25/mes | Más datos, backups, auth serio |
| **Storage** (Supabase/S3) | PDFs fuera del disco efímero | Free tier pequeño | Pay-as-you-go | Deploy cloud obligatorio |

**Mínimo viable en producción ligera (orden de magnitud):**  
~$0–15/mes (free + sleep) para pruebas internas → **~$40–80/mes** para algo presentable (API siempre up + Supabase Pro + storage).

### 4.2 Inteligencia / extracción (el costo variable del producto)

| Servicio | Para qué | Señal de costo | Plan / tip |
|----------|----------|----------------|------------|
| **LlamaParse** | OCR PDF / tablas bancarias | Por página / créditos | Free para probar → **pago al subir volumen de estados** |
| **OpenAI** | Facturas, estructura, embeddings CoA | Tokens | Pay-as-you-go; fijar modelo barato para clasificación |
| **Groq** | Whisper (audio) | Minutos / requests | Free/low; validar antes de depender |
| **Google Cloud / Drive API** | Drive OAuth + download | Quota API (suele free generoso) | Proyecto GCP en producción + OAuth HTTPS |

**Regla de gasto:** no contratar stacks “AI bookkeeping” que dupliquen LlamaParse + OpenAI + Supabase. Preferir **subir el plan de lo que ya está cableado** cuando el sprint de ese canal esté *full verificado*.

### 4.3 Registro de gasto del proyecto (llenar en cada sprint)

| Fecha | Vendor | Plan | USD/mes o uso | Motivo | Aprobado por |
|-------|--------|------|---------------|--------|--------------|
| — | — | — | — | — | — |

### 4.4 (Futuro) Planes del producto LedgerAI hacia clientes

Idea (no cerrada; la empresa decide):

| Plan producto | Incluye (borrador) | Precio (TBD) |
|---------------|--------------------|--------------|
| Cleanup puntuales | 1 espacio, N docs/mes, Drive + upload | TBD |
| Contabilidad continua | Varios espacios, cierre mensual, P&L | TBD |
| Estudio / white-label | Multi-cliente, SSO, SLA | TBD |

Los costos de §4.1–4.2 alimentan el margen de estos planes.

---

## 5. Producto web: PC + celular

- **Responsive** obligatorio en pantallas de trabajo (Documentos, Transacciones, Conciliación).  
- Móvil: subir foto de recibo / PDF del banco sin pasar por Drive.  
- PWA (instalar en teléfono) = sprint futuro tras upload móvil estable.  
- Drive sigue siendo potente para carpetas históricas; **no es el único camino**.

---

## 6. Despliegue internet (cuando toque el sprint)

Vercel = UI. API = Render/Railway/Fly (timeouts + background jobs). Supabase = datos.

Detalle checklist / env vars: mantener actualizado abajo.

### Env (nunca en git)

`SUPABASE_*`, `OPENAI_API_KEY`, `LLAMA_CLOUD_API_KEY`, `GROQ_API_KEY`, Google OAuth, `PORT`, CORS del origen Vercel.

### Checklist deploy

- [ ] Build frontend + API health  
- [ ] OAuth Drive con redirect HTTPS  
- [ ] Jobs OCR async (no cortar a 30s)  
- [ ] Storage cloud (no solo `/tmp`)  
- [ ] Auth si hay usuarios reales  

---

## 7. Compras futuras — criterio

¿Hace el pipeline **más fluido y verificable** (menos fallos OCR, menos espera, mejor UX móvil)?  
Si no → no comprar.

Prioridad de pago típica:

1. API hosting despierto (Render Starter)  
2. LlamaParse / OpenAI según volumen real medido  
3. Supabase Pro + Storage  
4. Vercel Pro solo si hace falta  

---

## 8. Feedback de la empresa (log)

Cada decisión de negocio que mueva el backlog:

| Fecha | Quién / tema | Decisión | Sprint impactado |
|-------|--------------|----------|------------------|
| — | — | — | — |

---

## 9. Principios técnicos (siempre)

- Arquitectura limpia: use cases / repos / API / UI separados  
- Clean code: sin demos eternas, sin secretos en repo  
- Observabilidad de pipeline: carpeta, tipo, APIs, preview de extracción  
- Full verificado > feature a medias  

---

*LedgerAI — parámetros vivos. Actualizar al cerrar sprints y al hablar con la empresa.*

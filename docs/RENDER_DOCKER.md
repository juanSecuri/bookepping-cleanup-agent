# Render — LedgerAI (Docker, Starter + disco persistente)

**Servicio actual (Docker + Tesseract):**  
https://dashboard.render.com/web/srv-da7j2pdg1s2s738243cg  

**URL:** https://ledgerai-0wyy.onrender.com  

Runtime: **Docker** (`./Dockerfile`) — incluye `tesseract-ocr` + `ffmpeg`.  
Plan: **Starter** · Oregon · auto-deploy desde `main`.

## Disco persistente (uploads)

Free usaba filesystem **efímero** (los uploads desaparecían al reiniciar → “Archivo no disponible en disco”).  
En **Starter** montamos un disco en `/var/data` y la app escribe en `LEDGERAI_UPLOAD_DIR=/var/data/ledgerai_uploads`.

La cola async corre **en el mismo proceso web** (poller en lifespan). No hay Background Worker aparte: un disco de Render **no se comparte** entre servicios. Supabase Storage queda como opción futura multi-instancia.

`render.yaml` declara `plan: starter`, `disk`, `healthCheckPath: /health` y `LEDGERAI_UPLOAD_DIR`.  
**MCP/API de Render no puede adjuntar el disco a un servicio ya creado** — hay que hacerlo en Dashboard (pasos abajo).

## Health

`GET https://ledgerai-0wyy.onrender.com/health`

**Acción manual (Juan):** Dashboard → servicio `ledgerai` → **Settings → Health Checks** → path **`/health`** → Save.

## Env requeridas (Dashboard → Environment)

| Key | Valor |
|-----|--------|
| `SUPABASE_URL` | (secreto) |
| `SUPABASE_SERVICE_ROLE_KEY` | (secreto) |
| `EXTRACTION_MODE` | `local` |
| `WHISPER_BACKEND` | `auto` |
| `LEDGERAI_UPLOAD_DIR` | `/var/data/ledgerai_uploads` |
| `GOOGLE_OAUTH_*` | (Drive, opcional) |
| `GROQ_API_KEY` | (opcional) |

No guardes secretos en git.

## Checklist Dashboard (servicio existente)

1. **Plan:** ya debería ser Starter (`serviceDetails.plan: starter`). Si no: Settings → Change plan → Starter.
2. **Disks** → Add disk:
   - Name: `ledgerai-uploads` (o el que quieras)
   - Mount path: `/var/data`
   - Size: `1` GB (se puede subir después; no bajar)
   - Add disk → redeploy automático
3. **Environment** → Add/Edit `LEDGERAI_UPLOAD_DIR` = `/var/data/ledgerai_uploads` → Save
4. **Settings → Health Checks** → `/health` → Save
5. Tras el deploy: subir un PDF, reiniciar el servicio, y confirmar que el preview/archivo sigue disponible.

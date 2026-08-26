# Render — LedgerAI (Docker, un solo servicio)

**Servicio actual (Docker + Tesseract):**  
https://dashboard.render.com/web/srv-da7j2pdg1s2s738243cg  

**URL:** https://ledgerai-0wyy.onrender.com  

Runtime: **Docker** (`./Dockerfile`) — incluye `tesseract-ocr` + `ffmpeg`.  
Plan: Free · Oregon · auto-deploy desde `main`.

## Health

`GET https://ledgerai-0wyy.onrender.com/health`

`render.yaml` declara `healthCheckPath: /health`. En el servicio ya creado el campo puede quedar vacío (la API/MCP de Render no lo edita en servicios existentes).

**Acción manual (Juan):** Dashboard → servicio `ledgerai` → **Settings → Health Checks** → path **`/health`** → Save.  
Así Render deja de marcar deploys unhealthy por falta de probe.

## Env requeridas (Dashboard → Environment)

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `EXTRACTION_MODE=local`, `WHISPER_BACKEND=auto`
- `GOOGLE_OAUTH_*` (Drive)
- opcional: `GROQ_API_KEY` (audio más fiable en Free 512MB)

No guardes secretos en git.

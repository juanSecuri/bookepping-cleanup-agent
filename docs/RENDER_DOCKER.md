# Render — LedgerAI (Docker, un solo servicio)

**Servicio actual (Docker + Tesseract):**  
https://dashboard.render.com/web/srv-da7j2pdg1s2s738243cg  

**URL:** https://ledgerai-0wyy.onrender.com  

Runtime: **Docker** (`./Dockerfile`) — incluye `tesseract-ocr` + `ffmpeg`.  
Plan: Free · Oregon · auto-deploy desde `main`.

## Health

`GET https://ledgerai-0wyy.onrender.com/health`

## Env requeridas (Dashboard → Environment)

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `EXTRACTION_MODE=local`, `WHISPER_BACKEND=auto`
- `GOOGLE_OAUTH_*` (Drive)
- opcional: `GROQ_API_KEY` (audio más fiable en Free 512MB)

No guardes secretos en git.

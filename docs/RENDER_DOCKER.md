# Render — pasar LedgerAI a Docker (OCR Tesseract)

El servicio **ledgerai** hoy corre como **Python nativo**. Para fotos (Tesseract) hace falta el binario del sistema → **Docker**.

El repo ya tiene `Dockerfile` + `render.yaml` con `runtime: docker`.

## Pasos en el Dashboard (1 vez, ~2 min)

1. Abre el servicio: https://dashboard.render.com/web/srv-da6h3r0u01pc7383bo60  
2. **Settings** → **Build & Deploy**  
3. **Runtime** → cambia de **Python 3** a **Docker**  
4. Confirma:
   - **Dockerfile Path:** `./Dockerfile` (o `Dockerfile`)
   - **Docker Context:** `.`
5. **Health Check Path:** `/health`  
6. Guarda (**Save Changes**) — Render redesplegará solo.

## Variables de entorno (ya configurables)

| Key | Valor recomendado |
|-----|-------------------|
| `EXTRACTION_MODE` | `local` |
| `WHISPER_BACKEND` | `auto` |
| `SUPABASE_URL` | (ya debe estar) |
| `SUPABASE_SERVICE_ROLE_KEY` | (ya debe estar) |
| `GOOGLE_OAUTH_*` | (si usas Drive) |
| `GROQ_API_KEY` | opcional — audio gratis vía Groq si no cabe whisper en 512MB |

## Verificar

- URL: https://ledgerai-6ate.onrender.com  
- `GET /health` → 200  
- UI YASNAY (verde + champagne)  
- Subir una foto de factura → debe OCR (no error “Tesseract binary missing”)

## No hace falta

- Crear otro servicio  
- Blueprint nuevo (salvo que quieras sincronizar el YAML completo)

# LedgerAI — Arquitectura (MVP SaaS)

Capas limpias; el monolito FastAPI en `apps/api/main.py` expone HTTP y delega en casos de uso.

```
frontend/          React + Vite (SPA, Supabase Auth)
apps/api/          FastAPI routes, static dist
src/
  domain/          Modelos, enums, excepciones
  use_cases/       Lógica de negocio (ingest, process_statement, reports…)
  infrastructure/  OCR, repos Supabase, cola, clasificación, reconciliación
  api/             Auth JWT helpers
migrations/        SQL Supabase
tests/             unit + integration
docs/              Parámetros, deploy, auth
```

## Pipeline documentos

1. Upload/Drive → `DocumentRepository` (`pending`)
2. `document_worker` (async loop, lock 1-a-1) reclama fila
3. Extracción según `pipeline_kind`:
   - **statement** → `ProcessStatementUseCase` (pdfplumber → Tesseract → reglas CoA → cadenazo)
   - **spreadsheet** → `SpreadsheetIngestUseCase`
   - **invoice** → `IngestDocumentUseCase` (imagen Tesseract, PDF local, audio whisper)
4. Estado `extracted` / `failed` + `apis_used` trazable

## OCR ($0)

| Entrada | Motor |
|---------|--------|
| PDF con texto | pdfplumber |
| PDF escaneado | pdfplumber vacío/corto → **Tesseract** por página |
| Imagen | Tesseract eng+spa |
| Excel/CSV | openpyxl |

Ver `src/infrastructure/ocr/`.

## Deploy

Render **Starter** + disco `/var/data` → `LEDGERAI_UPLOAD_DIR`. Ver `docs/RENDER_DOCKER.md`.

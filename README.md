# LedgerAI — Bookkeeping Cleanup Agent

**The Profit Catalyst (TPC)** · Producto mínimo viable (PMV) para limpieza contable  
**Live:** https://ledgerai-0wyy.onrender.com  
**Repo:** https://github.com/juanSecuri/bookepping-cleanup-agent

Organiza años de contabilidad atrasada: ingesta (Drive / web / foto / audio) → lectura local → clasificación por plan de cuentas (reglas, **$0 APIs IA**) → conciliación banco×mes → emisión de **Balance Sheet**, **P&L** y **Cash Flow** (mensual / anual, estilo QuickBooks).

> Fuente de verdad = datos del workspace (Drive / extractos). Los Excel/CSV de QuickBooks son **plantilla de formato / CoA de referencia**, no se importan como saldos.

---

## Decálogo — componentes del mercado (PMV)

| # | Componente | Qué es en LedgerAI | Estado PMV |
|---|------------|--------------------|------------|
| 1 | **Ingesta multi-canal** | Google Drive jerárquico, upload web PC/móvil, Excel/CSV, PDF, imagen OCR, audio | ✅ |
| 2 | **Extracción local ($0)** | pdfplumber → Tesseract; openpyxl/csv; sin LlamaParse/OpenAI obligatorios | ✅ |
| 3 | **Cola 1-archivo** | Worker secuencial (Render Free 512MB / OOM-safe) | ✅ |
| 4 | **Plan de cuentas (CoA)** | Seed TPC + reglas keywords; Suspense 9999; aprendizaje pasivo al corregir | ✅ |
| 5 | **Clasificación bank stmt** | Meals, Gas & Oil, Social Media Ads, Parking & Tolls, Insurance, Bank charges, Owner’s Distributions | ✅ (Sprint 16) |
| 6 | **Conciliación** | Banco × mes; match movimientos; cadenazo de saldos | ✅ |
| 7 | **Estados financieros** | P&L + Balance (columnas mes / Total anual) + Cash Flow O/I/F | ✅ |
| 8 | **Export CPA** | Excel 4 pestañas (P&L, Balance, Cash Flow, Transacciones) | ✅ |
| 9 | **Web responsive** | Navegador PC/móvil; cold-start banner (Render Free + Supabase Free) | ✅ |
| 10 | **Auth / multi-usuario** | Supabase JWT + membership (scaffold); invites/roles = backlog v2.1 | 🟡 parcial |

### Fuera de alcance PMV (backlog consciente)

- Formularios IRS / tax packs  
- Contabilidad de doble partida completa (hoy: cash-proxy + CoA)  
- PWA / app store  
- Embeddings / LLM de pago como dependencia  

---

## Stack

| Capa | Tecnología |
|------|------------|
| API | FastAPI + Docker en Render Free |
| UI | React + Vite (served desde el mismo servicio) |
| DB / Auth / Storage | Supabase Free |
| OCR | Tesseract eng+spa |
| Clasificación | `account_rules` deterministas (`rule_coa.py`) |

Parámetros vivos del producto: [`docs/PROJECT_PARAMETERS.md`](docs/PROJECT_PARAMETERS.md)  
Handoff CPA 2025: [`docs/HANDOFF_SPRINT_14_CPA_2025.md`](docs/HANDOFF_SPRINT_14_CPA_2025.md)  
Auth: [`docs/AUTH.md`](docs/AUTH.md)

---

## Arranque local

```bash
# Python
uv sync --extra dev
cp .env.example .env   # SUPABASE_URL + SERVICE_ROLE_KEY

# API
uv run python run.py

# Frontend (dev)
cd frontend && npm ci && npm run dev
```

Seed CoA + reglas ($0):

```bash
uv run python -m apps.cli.seed_coa --tenant <workspace-uuid>
# o desde UI: Plan de cuentas → Sembrar + Sembrar reglas
```

Tras reglas nuevas: **Transacciones → Re-categorizar con reglas**.

---

## Pipeline

```
Drive/Upload → cola → extracción local → classify(CoA)
  → conciliación banco×mes → Reportes (P&L / Balance / Cash flow) → Export Excel
```

---

## Licencia / marca

Producto de **The Profit Catalyst**. Nombre de producto: **LedgerAI**.

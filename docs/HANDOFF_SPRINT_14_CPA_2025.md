# Handoff Sprint 14 — CPA / SPA Taxes 2025

**Fecha:** 2026-09-08  
**Producto:** LedgerAI (TPC) — bookkeeping cleanup agent  
**Repo:** https://github.com/juanSecuri/bookepping-cleanup-agent  
**Live:** https://ledgerai-0wyy.onrender.com  
**Commit:** `72fa855` — `feat(cpa): Sprint 14 taxes 2025 — CoA direction, BS sections, P&L drill, bank×month recon`  
**Deploy Render:** servicio `ledgerai` (`srv-da7j2pdg1s2s738243cg`), auto-deploy desde `main`  
**Quién implementó:** Juan (Cursor / Composer), no Claude Code  
**Fuente de verdad del producto:** `docs/PROJECT_PARAMETERS.md`

---

## 1. Contexto para quien revise (tia / CPA / Claude)

La empresa necesita **estados financieros 2025** para pasar al **CPA/SPA** y elaborar taxes.  
LedgerAI ya tenía pipeline MVP (Drive/PDF → extracción local → clasificar CoA → conciliar → P&L/Balance/Cash flow + Excel).  

El **Sprint 14 (2026-09-08)** cerró los huecos críticos para ese paquete CPA:

1. Categorizar bien gastos no categorizados (proveedor/keywords) e **ingresos a cuentas de ingreso** (no a Cash).
2. **Balance general** organizado (Activo / Pasivo / Patrimonio) con cuentas del plan.
3. **P&L** con detalle al hacer click en una cuenta (ingresos, COGS, gastos).
4. **Conciliación banco × mes** (estilo QuickBooks).
5. Reportes **año / mes** + export Excel para el contador.

**Constraint de costos (no negociable):** el flujo principal funciona **sin APIs de IA de pago** (reglas + parsers + Tesseract). LLM pago solo como fallback opcional.

---

## 2. Qué se pidió (empresa → Juan)

Mensaje de cambios 2026-09-08:

1. Gastos no categorizados: buscar proveedor, a qué corresponde, categorizar la transacción.
2. Si recibe pago por ingresos → categorizar a cuenta de ingresos.
3. Reportes → Balance general con todas las cuentas (activo, pasivos, patrimonio, etc.).
4. Profit & Loss → al entrar a cuenta de ingresos mostrar detalle; igual para costos de ventas y gastos.
5. Conciliaciones banco por banco, mes por mes; al categorizar, detalle banco por banco (igual en conciliaciones).
6. En reportes ver año y mes a mes (como QuickBooks), para CPA/SPA taxes **2025**.

---

## 3. Qué se entregó (resumen ejecutivo)

| # | Pedido | Estado | Cómo se ve / se usa |
|---|--------|--------|---------------------|
| 1 | Gastos sin categoría → proveedor + CoA | Hecho | Transacciones → “No categorizadas” / “Pendientes” → botón **Re-categorizar con reglas**; o asignar cuenta manual (aprende keyword). |
| 2 | Pagos/ingresos → cuenta ingresos | Hecho | Créditos bancarios clasifican con `direction=income` → 4010/4020/4030/4040 (ya no Cash 1010 por defecto). |
| 3 | Balance completo | Hecho | Reportes → Balance con secciones por subgrupo CoA (Current Assets, Fixed Assets, Current Liabilities, LT Liabilities, Equity); incluye cuentas en cero. |
| 4 | P&L con detalle | Hecho | Click en fila de ingresos / COGS / gastos → modal con transacciones del periodo. |
| 5 | Conciliación banco×mes | Hecho | Conciliación → selectores Banco / Año / Mes; tabla con CoA, confianza %, match/unmatch; franja de saldos/cadenazo si hay periodo. |
| 6 | Año/mes + CPA | Hecho | Selector año/mes en Reportes (default **2025** si hay datos); **Export Excel** 4 pestañas (P&L, Balance, Cash Flow, Transacciones). |

**Tests locales al cerrar:** 59 unit tests OK + frontend `tsc` OK.

---

## 4. Detalle técnico (para Claude u otro agente)

### 4.1 Clasificación CoA (T1)

**Archivos clave:**
- `src/infrastructure/classification/rule_coa.py`
- `src/use_cases/process_statement.py`
- `src/use_cases/ingest_spreadsheet.py`
- `src/use_cases/ingest_document.py`
- `apps/api/main.py` → `POST /api/transactions/recategorize`
- `frontend/src/pages/app/Transactions.tsx`

**Comportamiento:**
- `classify(tenant_id, description, direction="income"|"expense")`.
- Débito bancario → `expense`; crédito → `income`.
- Ingresos: prioriza cuentas `4010–4040`; **bloquea** mapear a Cash `1010` / gastos / suspense cuando `direction=income`.
- Sin match en ingreso → default **`4040 Other Income`** (confianza ~0.35), no Suspense 9999.
- Sin match en gasto → **`9999` Suspense** (“Gastos No Categorizados”).
- `extract_vendor()` + match de keywords (seed + learned).
- `upgrade_income_seed_rules()`: corrige seeds legacy que mandaban payment/deposit/stripe/paypal → 1010 hacia ingresos.
- Campo de confianza en DB/UI: **`category_confidence`** (no existe columna `transactions.confidence`).

**API útil:**
- `POST /api/transactions/recategorize` `{ workspace_id, only_suspense: true }` — re-corre reglas en suspense / baja confianza / ingresos pendientes mal en 1010. **No auto-verifica.**

### 4.2 Balance general (T2)

**Archivo:** `src/use_cases/emit_period_reports.py`

- Carga CoA con `subcategory`.
- Fusiona cuentas asset/liability/equity del plan aunque saldo = 0.
- Emite `balance_sheet.sections`: grupos por subcategoría (estilo QuickBooks).
- Mantiene ecuación **A = P + E** + utilidad del ejercicio en 3020 + RE años cerrados en `3020-PY`.
- Cash sigue siendo proxy operativo; activos no-caja (ej. equipo) suben si hay txs investing clasificadas a esa cuenta.

### 4.3 P&L drill-down (T3)

**API:** `GET /api/transactions?tenant_id&account_code&date_from&date_to&status=verified,closed`  
**UI:** `frontend/src/pages/app/Reports.tsx` — click fila → modal detalle.

### 4.4 Conciliación banco × mes (T4)

**API:**
- `GET /api/reconciliation/banks?workspace_id=`
- `GET /api/movements?workspace_id&bank_name&bank_account_number&statement_month=`

**Repo:** `list_filtered` con **paginación `.range()`** (evita truncar por límite ~1000 de PostgREST).  
**UI:** `frontend/src/pages/app/Reconciliation.tsx`

### 4.5 Periodo / export CPA (T5)

- Año/mes en Reportes (desde Sprint 13a; Sprint 14 prefiere default **2025**).
- `GET /api/reports/export.xlsx?workspace_id&fiscal_year&month=` → 4 sheets.

### 4.6 Tests nuevos / tocados

- `tests/unit/test_rule_coa.py`
- `tests/unit/test_balance_sections.py`
- `tests/unit/test_emit_period_2024.py` (ajustes)

---

## 5. Flujo recomendado para preparar el paquete CPA 2025

1. Abrir workspace en https://ledgerai-0wyy.onrender.com (tras deploy `live`).
2. Sembrar / actualizar reglas: CoA + **Seed rules** (el seed también hace upgrade de reglas 1010→ingresos).
3. **Transacciones → No categorizadas / Pendientes → Re-categorizar con reglas**.
4. Revisar sugerencias; **Asignar cuenta** donde falte (el sistema aprende keywords).
5. **Aprobar** (verified) lo correcto — los reportes usan txs **verified/closed**.
6. **Reportes → año 2025** (mes vacío = año completo) → revisar P&L, Balance, Cash flow.
7. Click en cuentas del P&L para auditar detalle.
8. **Export Excel** → entregar al CPA/SPA.
9. **Conciliación** → banco × mes para soporte de extractos.

---

## 6. Riesgos conscientes (backlog, no bloquean el sprint)

Documentados en revisión de bugs post-implementación:

| Riesgo | Nota |
|--------|------|
| Recategorize con `only_suspense` | No corrige CoA “mal pero con alta confianza” salvo income pendiente en 1010. |
| Créditos vs keywords equity/pasivo | Un crédito podría matchear “owner draw” / pasivo si el texto solapa. |
| Bancos sin `bank_account_number` (≥4 chars) | No aparecen en el picker de conciliación. |
| Link “Ver en Transacciones” desde drill | No pasa aún filtros account/date en la URL. |
| Facturas OCR siempre `direction=expense` | Credit memos / refunds raros pueden mal clasificarse. |
| Balance cash-proxy | No es un BS de contabilidad completa por asientos dobles; es el modelo cash+CoA del producto. |

---

## 7. Qué NO se hizo a propósito (Sprint 14)

- Formularios IRS / tax forms.
- Multi-entity / binders PDF.
- Auth multi-usuario completo (invites/roles) — sigue v2.1.
- Dependencia de OpenAI/LlamaParse para el camino feliz.

---

## 8. Historia de sprints relevante (orden)

| Sprint | Tema | Estado |
|--------|------|--------|
| 0–13e | Pipeline $0, cola, CoA rules, cadenazo, reportes SQL, OCR, Storage, marca TPC | DONE |
| **14** | **CPA Taxes 2025 (este handoff)** | **DONE en código; smoke en prod tras deploy** |

Log empresa: ver sección 8 de `docs/PROJECT_PARAMETERS.md` (fila **2026-09-08**).

---

## 9. Instrucciones para Claude (cuando la tía revise)

Si estás en Claude y te piden revisar o continuar este trabajo:

1. Lee primero **`docs/PROJECT_PARAMETERS.md`** y **este handoff**.
2. No reinventar el producto: constraint **$0 APIs IA**, un foco por sprint, DoD *full verificado*.
3. El código de Sprint 14 ya está en `main` (`72fa855`); verificar deploy Render live antes de asumir UI vieja.
4. Para bugs: priorizar calidad de categorización 2025 y reportes CPA, no features nuevas (PWA, counters, etc.).
5. Juan desarrolla en **Cursor**, no en Claude; este documento es el puente de contexto.

---

## 10. Checklist rápido de revisión (tia / CPA)

- [ ] Deploy Render en estado **live** con commit `72fa855` (o posterior).
- [ ] Hay datos 2025 (txs / extractos) en el workspace.
- [ ] Re-categorizar + aprobar dejó pocos `9999` suspense.
- [ ] Ingresos aparecen en P&L (4010–4040), no como Cash.
- [ ] Balance muestra Activo / Pasivo / Patrimonio y cuadre A≈P+E.
- [ ] Click en una cuenta del P&L muestra txs del periodo.
- [ ] Conciliación filtra por banco y mes.
- [ ] Excel exportado abre 4 hojas y sirve para el contador.

---

*Documento generado 2026-09-08 para handoff humano + Claude. Actualizar si hay hotfix post-deploy.*

# LedgerAI v1.0.0

First reviewable release of the bookkeeping cleanup agent.

## What it does
- Ingest PDFs/Excel from Google Drive (nested folders: bank → account → year)
- Classify: bank statement vs invoice vs spreadsheet
- Extract with LlamaParse + structure with OpenAI; categorize via embeddings vs chart of accounts
- Review/approve transactions, reconcile bank movements, close periods
- Profit & loss (P&L): revenue − expenses for a date range

## Stack
FastAPI · React (Vite) · Supabase · Google Drive · LlamaParse · OpenAI · Groq (voice)

## Notes
- Workspaces are deletable (cascades docs / txs / movements / CoA)
- Documents show Drive folder provenance and APIs used
- Sidebar collapsible; dashboard explains the live agent pipeline

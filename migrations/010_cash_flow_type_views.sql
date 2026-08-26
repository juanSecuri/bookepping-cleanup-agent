-- cash_flow_type (O/I/F) + SQL report views
-- Applied remotely as: cash_flow_type_and_report_views

ALTER TABLE financial_transactions
  ADD COLUMN IF NOT EXISTS cash_flow_type TEXT
    CHECK (cash_flow_type IS NULL OR cash_flow_type IN ('operating', 'investing', 'financing'));

CREATE INDEX IF NOT EXISTS idx_ft_tenant_cf
  ON financial_transactions (tenant_id, cash_flow_type);

UPDATE financial_transactions ft
SET cash_flow_type = CASE
  WHEN ft.chart_of_accounts_code IN ('3010', '3020', '3030') THEN 'financing'
  WHEN EXISTS (
    SELECT 1 FROM chart_of_accounts c
    WHERE c.tenant_id = ft.tenant_id AND c.code = ft.chart_of_accounts_code
      AND c.account_type IN ('equity', 'liability')
  ) THEN 'financing'
  WHEN EXISTS (
    SELECT 1 FROM chart_of_accounts c
    WHERE c.tenant_id = ft.tenant_id AND c.code = ft.chart_of_accounts_code
      AND c.account_type = 'asset' AND c.code NOT IN ('1010', '1020')
  ) THEN 'investing'
  ELSE 'operating'
END
WHERE cash_flow_type IS NULL;

CREATE OR REPLACE VIEW v_tx_cash_flow AS
SELECT
  ft.id,
  ft.tenant_id,
  ft.transaction_date,
  ft.description,
  ft.amount,
  ft.currency,
  ft.transaction_type,
  ft.chart_of_accounts_code,
  ft.chart_of_accounts_name,
  ft.status,
  COALESCE(
    ft.cash_flow_type,
    CASE
      WHEN ft.chart_of_accounts_code IN ('3010', '3020', '3030') THEN 'financing'
      WHEN c.account_type IN ('equity', 'liability') THEN 'financing'
      WHEN c.account_type = 'asset'
           AND ft.chart_of_accounts_code NOT IN ('1010', '1020') THEN 'investing'
      ELSE 'operating'
    END
  ) AS cash_flow_type,
  COALESCE(c.account_type, 'expense') AS account_type,
  to_char(ft.transaction_date, 'YYYY-MM') AS period_month,
  to_char(ft.transaction_date, 'YYYY') AS period_year
FROM financial_transactions ft
LEFT JOIN chart_of_accounts c
  ON c.tenant_id = ft.tenant_id AND c.code = ft.chart_of_accounts_code
WHERE ft.status IN ('verified', 'closed');

CREATE OR REPLACE VIEW v_pnl_by_month AS
SELECT
  tenant_id,
  period_month AS period,
  SUM(CASE
        WHEN transaction_type = 'income'
             AND account_type NOT IN ('equity', 'liability')
             AND cash_flow_type = 'operating' THEN amount
        ELSE 0
      END) AS revenue,
  SUM(CASE
        WHEN transaction_type = 'expense'
             AND account_type NOT IN ('equity', 'liability')
             AND cash_flow_type = 'operating' THEN amount
        ELSE 0
      END) AS expenses,
  SUM(CASE
        WHEN transaction_type = 'income'
             AND account_type NOT IN ('equity', 'liability')
             AND cash_flow_type = 'operating' THEN amount
        ELSE 0
      END)
  - SUM(CASE
          WHEN transaction_type = 'expense'
               AND account_type NOT IN ('equity', 'liability')
               AND cash_flow_type = 'operating' THEN amount
          ELSE 0
        END) AS net_income,
  COUNT(*) AS tx_count
FROM v_tx_cash_flow
GROUP BY tenant_id, period_month;

CREATE OR REPLACE VIEW v_cash_flow_by_month AS
SELECT
  tenant_id,
  period_month AS period,
  cash_flow_type,
  SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE 0 END) AS inflows,
  SUM(CASE WHEN transaction_type = 'expense' THEN amount ELSE 0 END) AS outflows,
  SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE -amount END) AS net,
  COUNT(*) AS tx_count
FROM v_tx_cash_flow
GROUP BY tenant_id, period_month, cash_flow_type;

CREATE OR REPLACE VIEW v_balance_equity_proxy AS
SELECT
  tenant_id,
  period_year AS fiscal_year,
  SUM(CASE
        WHEN transaction_type = 'income' AND cash_flow_type = 'operating' THEN amount
        ELSE 0
      END)
  - SUM(CASE
          WHEN transaction_type = 'expense' AND cash_flow_type = 'operating' THEN amount
          ELSE 0
        END) AS period_net_income,
  SUM(CASE
        WHEN cash_flow_type = 'financing' AND transaction_type = 'expense' THEN amount
        ELSE 0
      END)
  - SUM(CASE
          WHEN cash_flow_type = 'financing' AND transaction_type = 'income' THEN amount
          ELSE 0
        END) AS net_draws,
  SUM(CASE WHEN transaction_type = 'income' THEN amount ELSE -amount END) AS cash_proxy
FROM v_tx_cash_flow
GROUP BY tenant_id, period_year;

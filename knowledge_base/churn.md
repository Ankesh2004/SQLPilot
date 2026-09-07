# Churn Rate

## Definition
Churn rate measures the percentage of customers who cancelled their subscriptions during a given period.

## Formula
```sql
-- churn rate for a specific month (e.g., 2026-01)
SELECT
    ROUND(
        CAST(COUNT(CASE WHEN status = 'cancelled'
                        AND end_date >= '2026-01-01'
                        AND end_date < '2026-02-01' THEN 1 END) AS FLOAT)
        /
        NULLIF(COUNT(CASE WHEN start_date < '2026-01-01'
                          AND (end_date IS NULL OR end_date >= '2026-01-01')
                          AND status IN ('active', 'cancelled') THEN 1 END), 0)
        * 100
    , 2) AS churn_rate_pct
FROM subscriptions
```

## Important Notes
- The denominator is **total active subscriptions at the start of the period** (not total customers ever)
- A customer who signed up AND cancelled in the same month still counts as churn
- Trial subscriptions that expire do NOT count as churn — they were never "active"
- Only look at `subscriptions` table, not `customers` table

## Common Confusions
- "Customer churn" vs "Revenue churn" are different things
  - Customer churn = count of cancelled / count of active
  - Revenue churn = MRR lost from cancellations / total MRR
- When someone just says "churn", they usually mean **customer churn rate**
- The time period matters a lot — always clarify monthly vs quarterly vs annual

## Related Metrics
- **Retention Rate** = 100% - Churn Rate
- **Net Revenue Retention (NRR)** = (MRR at end + expansion - contraction - churn) / MRR at start

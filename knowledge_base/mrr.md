# Monthly Recurring Revenue (MRR)

## Definition
MRR is the total predictable monthly revenue from all active, paying subscriptions.

## Formula
```sql
SELECT SUM(monthly_fee) AS mrr
FROM subscriptions
WHERE status = 'active'
  AND status != 'trial'
```

## Important Notes
- **Exclude trials**: subscriptions with `status = 'trial'` are NOT counted in MRR
- **Exclude paused**: `status = 'paused'` subscriptions are NOT counted (they aren't generating revenue right now)
- **Exclude cancelled**: obviously, `status = 'cancelled'` means no revenue
- Only `status = 'active'` contributes to MRR

## Common Confusions
- MRR is NOT the same as invoice amounts — invoices can include tax, discounts, and one-time charges
- MRR is calculated from `subscriptions.monthly_fee`, not from `invoices.amount`
- If someone asks "what's our revenue", they might mean MRR or total invoiced amount — clarify first

## Related Metrics
- **ARR** (Annual Recurring Revenue) = MRR × 12
- **Net MRR** = new MRR + expansion MRR - churned MRR - contraction MRR

# Revenue

## The Ambiguity Problem
"Revenue" is one of the most ambiguous terms in our database. It can mean several different things depending on who's asking.

## Possible Interpretations

### 1. Gross Revenue (Total Invoiced)
The total amount billed to customers, before any deductions.
```sql
SELECT SUM(amount) AS gross_revenue
FROM invoices
WHERE payment_status = 'paid'
```

### 2. Net Revenue (After Tax & Discounts)
What we actually keep after subtracting tax and discounts.
```sql
SELECT SUM(amount - tax - discount) AS net_revenue
FROM invoices
WHERE payment_status = 'paid'
```

### 3. MRR (Monthly Recurring Revenue)
Predictable monthly subscription revenue. See [mrr.md](mrr.md) for full definition.
```sql
SELECT SUM(monthly_fee) AS mrr
FROM subscriptions
WHERE status = 'active' AND status != 'trial'
```

### 4. Total Collected Revenue
All money that has actually been received (paid invoices only, no pending/overdue).
```sql
SELECT SUM(amount) AS collected_revenue
FROM invoices
WHERE payment_status = 'paid'
  AND paid_date IS NOT NULL
```

## When to Clarify
If a user asks about "revenue" without specifying which type, **always ask for clarification**.
Suggested options:
1. MRR from active subscriptions
2. Total invoiced amount (gross)
3. Net revenue after tax and discounts
4. Collected revenue (actually paid)

## Key Differences
| Type | Source Table | Includes Tax? | Includes Unpaid? |
|------|-------------|---------------|------------------|
| Gross Revenue | invoices | Yes | No (paid only) |
| Net Revenue | invoices | No (subtracted) | No (paid only) |
| MRR | subscriptions | No | N/A |
| Collected | invoices | Yes | No |

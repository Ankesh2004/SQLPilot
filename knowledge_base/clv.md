# Customer Lifetime Value (CLV)

## Definition
CLV estimates the total revenue a business can expect from a single customer account over their entire relationship.

## Simple Formula
```sql
-- average total revenue per customer (historical)
SELECT AVG(total_paid) AS avg_clv
FROM (
    SELECT
        c.id,
        SUM(i.amount - i.tax - i.discount) AS total_paid
    FROM customers c
    JOIN subscriptions s ON s.customer_id = c.id
    JOIN invoices i ON i.subscription_id = s.id
    WHERE i.payment_status = 'paid'
    GROUP BY c.id
) customer_totals
```

## Per-Customer CLV
```sql
SELECT
    c.id,
    c.name,
    c.company,
    SUM(i.amount - i.tax - i.discount) AS lifetime_value
FROM customers c
JOIN subscriptions s ON s.customer_id = c.id
JOIN invoices i ON i.subscription_id = s.id
WHERE i.payment_status = 'paid'
GROUP BY c.id, c.name, c.company
ORDER BY lifetime_value DESC
```

## Important Notes
- Uses net revenue (amount - tax - discount) from paid invoices only
- Refunded invoices (`payment_status = 'refunded'`) should be excluded
- This is historical CLV — predictive CLV would need a different model
- Joins through subscriptions to invoices (customers → subscriptions → invoices)

## Related Metrics
- **ARPU** (Average Revenue Per User) = total revenue / count of customers
- **LTV:CAC Ratio** = CLV / Customer Acquisition Cost (we don't track CAC in this schema)

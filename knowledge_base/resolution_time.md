# Support Ticket Resolution Time

## Definition
Average time it takes to resolve a customer support ticket, from creation to resolution.

## Formula
```sql
SELECT
    AVG(
        julianday(resolved_at) - julianday(created_at)
    ) * 24 AS avg_resolution_hours
FROM support_tickets
WHERE status IN ('resolved', 'closed')
  AND resolved_at IS NOT NULL
```

## By Priority Level
```sql
SELECT
    priority,
    COUNT(*) AS ticket_count,
    ROUND(AVG(julianday(resolved_at) - julianday(created_at)) * 24, 1) AS avg_hours
FROM support_tickets
WHERE status IN ('resolved', 'closed')
  AND resolved_at IS NOT NULL
GROUP BY priority
ORDER BY
    CASE priority
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        WHEN 'low' THEN 4
    END
```

## Important Notes
- Only tickets with `resolved_at IS NOT NULL` should be included
- Open and in-progress tickets don't have resolution times yet
- Time is calculated in hours using `julianday()` for SQLite; for PostgreSQL use `EXTRACT(EPOCH FROM ...)`
- "Response time" (first reply) is different from "resolution time" — we only track resolution here

## Common Confusions
- "How fast do we resolve tickets?" → this metric
- "How many tickets are open?" → different query, just count WHERE status = 'open'
- "What's our SLA compliance?" → we don't track SLA targets in this schema

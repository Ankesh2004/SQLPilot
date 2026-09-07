# Active Users

## The Ambiguity Problem
"Active user" has two very different meanings in our system.

## Interpretation 1: Active Subscription
Customer has a subscription with `status = 'active'`.
```sql
SELECT DISTINCT c.*
FROM customers c
JOIN subscriptions s ON s.customer_id = c.id
WHERE s.status = 'active'
```

## Interpretation 2: Recent Product Usage
Customer has used the product recently (logged in, made API calls, etc.) within a time window.
```sql
-- active in the last 30 days
SELECT DISTINCT c.*
FROM customers c
JOIN usage_events ue ON ue.customer_id = c.id
WHERE ue.timestamp >= date('now', '-30 days')
```

## When to Clarify
If a user asks about "active users" or "how many active customers", clarify:
1. Customers with active subscriptions (billing definition)
2. Customers with recent usage activity (engagement definition)
3. If engagement: what time window? (last 7 days, 30 days, 90 days)

## Important Notes
- A customer can have an active subscription but ZERO usage events (they're paying but not using the product — that's a churn risk)
- A customer can have lots of recent usage but be on a 'trial' or even 'cancelled' subscription (still has access during grace period)
- For board-level reporting, "active" usually means paid + subscription active
- For product teams, "active" usually means usage-based (DAU/MAU)
- Default to **last 30 days** if the user says "recent" without specifying

## Related Metrics
- **DAU** (Daily Active Users) = unique customers with usage_events today
- **MAU** (Monthly Active Users) = unique customers with usage_events in last 30 days
- **WAU** (Weekly Active Users) = unique customers with usage_events in last 7 days

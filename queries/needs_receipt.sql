-- used by snowball_ticketing.tickets.receipt
SELECT users.user_id, last_receipt, updated
FROM (
    SELECT
        user_id,
        MAX(GREATEST(finalised, paid)) AS updated,
        MAX(expires) AS next_expires
    FROM tickets
    GROUP BY user_id
) AS t
JOIN users ON users.user_id = t.user_id
WHERE 
    updated IS NOT NULL AND
    (last_receipt IS NULL OR last_receipt < updated) AND
    (next_expires IS NULL OR
     next_expires < utcnow() OR
     next_expires > utcnow() + '20 minutes'::interval)

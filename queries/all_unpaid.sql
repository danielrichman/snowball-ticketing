SELECT tickets, last_created, last_receipt, users.email
FROM (
    SELECT user_id, count(*) AS tickets, max(created) AS last_created
    FROM tickets
    WHERE finalised IS NOT NULL AND paid IS NULL AND NOT waiting_list
    GROUP BY user_id
) AS t
JOIN users ON users.user_id = t.user_id;

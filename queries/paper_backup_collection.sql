COPY (
    WITH
        sorted_tickets AS (SELECT * FROM tickets ORDER BY ticket_id),
        user_tickets AS (SELECT user_id, array_agg(ticket_id) AS ticket_ids FROM sorted_tickets WHERE paid IS NOT NULL GROUP BY user_id)

    SELECT users.surname, users.othernames, array_to_string(ticket_ids, ', ')
    FROM user_tickets JOIN users ON users.user_id = user_tickets.user_id
    ORDER BY surname
)
TO STDOUT CSV;

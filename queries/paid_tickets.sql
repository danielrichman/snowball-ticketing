COPY (
    SELECT
        users.user_id,
        tickets.ticket_id,
        CASE WHEN tickets.vip THEN 'VIP' END,
        users.othernames || ' ' || users.surname AS "user",
        users.email AS user_email,
        users.person_type AS "user_type",
        users_colleges.name AS "user_college",
        tickets.othernames || ' ' || tickets.surname AS guest,
        tickets.person_type AS "guest_type",
        tickets_colleges.name AS "guest_college",
        price,
        quota_exempt,
        created
    FROM tickets
    JOIN users ON tickets.user_id = users.user_id
    JOIN colleges AS users_colleges ON users.college_id = users_colleges.college_id
    LEFT OUTER JOIN colleges AS tickets_colleges ON tickets.college_id = tickets_colleges.college_id
    WHERE paid IS NOT NULL
    ORDER BY user_id, tickets.surname, tickets.othernames
)
TO STDOUT CSV;

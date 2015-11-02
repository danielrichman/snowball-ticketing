COPY (
    SELECT
        user_id,
        othernames || ' ' || surname AS "name",
        email,
        person_type,
        colleges.name AS "college",
        notes
    FROM users
    JOIN colleges ON users.college_id = colleges.college_id
    WHERE user_id IN (SELECT DISTINCT user_id FROM tickets WHERE paid IS NOT NULL)
    ORDER BY user_id
)
TO STDOUT CSV;

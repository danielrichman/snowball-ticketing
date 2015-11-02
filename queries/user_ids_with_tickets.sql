COPY (
    SELECT DISTINCT user_id
    FROM tickets
    WHERE paid IS NOT NULL
    ORDER BY user_id
) TO STDOUT;

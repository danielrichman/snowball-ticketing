WITH 
    a AS (
        SELECT count(*) AS paid_tickets, sum(price)/100 AS paid_amt
        FROM tickets WHERE paid IS NOT NULL
    ),
    b AS (
        SELECT count(*) AS all_tickets, sum(price)/100 AS all_amt
        FROM tickets WHERE finalised IS NOT NULL AND NOT waiting_list
    )
SELECT * FROM a, b

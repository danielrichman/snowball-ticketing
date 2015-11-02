-- this is a straight clone of snowball_ticketing/tickets/counts_query.sql
SELECT *,
    all_standard                + all_vip                   AS all_any
FROM (SELECT *,
    members_standard            + alumni_standard           AS all_standard,
    members_vip                 + alumni_vip                AS all_vip,
    members_standard            + members_vip               AS members_any,
    alumni_standard             + alumni_vip                AS alumni_any
FROM (SELECT
    COUNT(NULLIF(member  AND standard,   FALSE)) AS members_standard,
    COUNT(NULLIF(member  AND vip,        FALSE)) AS members_vip,
    COUNT(NULLIF(alumnus AND standard,   FALSE)) AS alumni_standard,
    COUNT(NULLIF(alumnus AND vip,        FALSE)) AS alumni_vip
FROM (
    SELECT users.person_type = 'alumnus' AS alumnus,
           users.person_type != 'alumnus' AS member,
           vip,
           NOT vip AS standard
    FROM tickets
    LEFT JOIN users ON users.user_id = tickets.user_id
    WHERE paid IS NOT NULL AND NOT quota_exempt
) AS t
) AS t2
) AS t3;

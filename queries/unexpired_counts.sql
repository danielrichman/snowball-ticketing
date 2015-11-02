-- used by snowball_ticketing.tickets.__init__
--
-- here, I use SELECT ... FROM (SELECT ... ) since it seems to make the query faster.
-- I suspect it allows the PostgreSQL query planner to aggregate/count the rows from the
-- innermost query as it produces them, rather than saving it to memory and scanning it again
SELECT *,
    all_standard                + all_vip                   AS all_any,
    waiting_all_standard        + waiting_all_vip           AS waiting_all_any
FROM (SELECT *,
    members_standard            + alumni_standard           AS all_standard,
    members_vip                 + alumni_vip                AS all_vip,
    waiting_members_standard    + waiting_alumni_standard   AS waiting_all_standard,
    waiting_members_vip         + waiting_alumni_vip        AS waiting_all_vip,
    members_standard            + members_vip               AS members_any,
    alumni_standard             + alumni_vip                AS alumni_any,
    waiting_members_standard    + waiting_members_vip       AS waiting_members_any,
    waiting_alumni_standard     + waiting_alumni_vip        AS waiting_alumni_any
FROM (SELECT
    COUNT(NULLIF(member  AND standard       AND NOT waiting_list,   FALSE)) AS members_standard,
    COUNT(NULLIF(member  AND standard       AND waiting_list,       FALSE)) AS waiting_members_standard,
    COUNT(NULLIF(member  AND vip            AND NOT waiting_list,   FALSE)) AS members_vip,
    COUNT(NULLIF(member  AND vip            AND waiting_list,       FALSE)) AS waiting_members_vip,
    COUNT(NULLIF(alumnus AND standard       AND NOT waiting_list,   FALSE)) AS alumni_standard,
    COUNT(NULLIF(alumnus AND standard       AND waiting_list,       FALSE)) AS waiting_alumni_standard,
    COUNT(NULLIF(alumnus AND vip            AND NOT waiting_list,   FALSE)) AS alumni_vip,
    COUNT(NULLIF(alumnus AND vip            AND waiting_list,       FALSE)) AS waiting_alumni_vip
FROM (SELECT users.person_type = 'alumnus' AS alumnus, users.person_type != 'alumnus' AS member,
             waiting_list, vip, NOT vip AS standard
    FROM tickets
    LEFT JOIN users ON users.user_id = tickets.user_id
    WHERE (expires IS NULL OR expires > utcnow()) AND NOT quota_exempt
) AS t
) AS t2
) AS t3;

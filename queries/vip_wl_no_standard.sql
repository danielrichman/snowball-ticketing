SELECT t.*, users.crsid, users.email FROM (
    SELECT othernames || ' ' || surname AS name,
           user_id,
           count(NULLIF(NOT vip AND NOT waiting_list, FALSE)) AS std,
           count(NULLIF(NOT vip AND waiting_list, FALSE)) AS std_wl,
           count(NULLIF(vip AND NOT waiting_list, FALSE)) AS vip,
           count(NULLIF(vip AND waiting_list, FALSE)) AS vip_wl,
           min(finalised) AS first,
           max(finalised) AS last
    FROM tickets
    WHERE finalised IS NOT NULL
    GROUP BY name, user_id
) AS t
JOIN users ON t.user_id = users.user_id
WHERE vip_wl > 0 AND NOT (vip_wl = 1 AND std = 1)
ORDER BY last;

SELECT date_trunc('hour', created) AS hour_bin, count(*)
FROM tickets WHERE finalised IS NOT NULL AND NOT waiting_list
GROUP BY hour_bin ORDER BY hour_bin

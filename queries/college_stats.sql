WITH
    colleges2 AS (SELECT college_id, name FROM colleges UNION SELECT -1, 'other'),
    guest_counts AS (SELECT count(*) AS guests, COALESCE(college_id, -1) AS college_id FROM tickets WHERE finalised IS NOT NULL AND NOT waiting_list GROUP BY college_id),
    team_leader_tickets_counts AS (SELECT count(*) AS team_leader_tickets, users.college_id FROM tickets LEFT JOIN users ON tickets.user_id = users.user_id WHERE finalised IS NOT NULL AND NOT waiting_list GROUP BY users.college_id),
    team_leaders AS (SELECT user_id FROM tickets WHERE finalised IS NOT NULL AND NOT waiting_list GROUP BY user_id),
    team_leader_counts AS (SELECT count(*) AS team_leaders, users.college_id FROM team_leaders LEFT JOIN users on users.user_id = team_leaders.user_id GROUP BY users.college_id)
SELECT colleges.name, guests, team_leader_tickets, team_leaders 
FROM colleges2 AS colleges
LEFT JOIN guest_counts ON colleges.college_id = guest_counts.college_id
LEFT JOIN team_leader_tickets_counts ON colleges.college_id = team_leader_tickets_counts.college_id
LEFT JOIN team_leader_counts ON colleges.college_id = team_leader_counts.college_id
ORDER BY colleges.name

-- Transfer window analysis
-- Breakdown by summer vs winter windows, trends over time

-- Transfer volume and spending by window
SELECT
    t.transfer_season AS season,
    CASE 
        WHEN t.transfer_date IS NOT NULL AND EXTRACT(MONTH FROM TRY_CAST(t.transfer_date AS DATE)) BETWEEN 6 AND 9 
        THEN 'Summer'
        WHEN t.transfer_date IS NOT NULL AND EXTRACT(MONTH FROM TRY_CAST(t.transfer_date AS DATE)) IN (1, 2) 
        THEN 'Winter'
        ELSE 'Other'
    END AS transfer_window,
    comp.name AS league_name,
    c.domestic_competition_id AS league_id,
    COUNT(*) AS num_transfers,
    SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS total_spending,
    AVG(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS avg_fee,
    MAX(t.transfer_fee) AS max_fee
FROM transfers t
JOIN clubs c ON CAST(t.to_club_id AS VARCHAR) = CAST(c.club_id AS VARCHAR)
LEFT JOIN competitions comp ON c.domestic_competition_id = comp.competition_id
WHERE t.transfer_season IS NOT NULL
GROUP BY t.transfer_season, transfer_window, comp.name, c.domestic_competition_id
ORDER BY t.transfer_season DESC, total_spending DESC;

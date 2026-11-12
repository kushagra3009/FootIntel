-- Club spending aggregated by season
-- Used by: spending_vs_success analysis

-- Total spending by club per season
SELECT
    t.transfer_season AS season,
    c.name AS club_name,
    c.domestic_competition_id AS league_id,
    comp.name AS league_name,
    COUNT(*) AS transfers_in,
    SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS total_spending,
    AVG(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS avg_fee_paid,
    MAX(t.transfer_fee) AS record_signing,
    SUM(CASE WHEN t.transfer_fee = 0 OR t.transfer_fee IS NULL THEN 1 ELSE 0 END) AS free_transfers
FROM transfers t
JOIN clubs c ON CAST(t.to_club_id AS VARCHAR) = CAST(c.club_id AS VARCHAR)
LEFT JOIN competitions comp ON c.domestic_competition_id = comp.competition_id
WHERE t.transfer_season IS NOT NULL
GROUP BY t.transfer_season, c.name, c.domestic_competition_id, comp.name
ORDER BY total_spending DESC;

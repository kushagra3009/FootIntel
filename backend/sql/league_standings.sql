-- League standings proxy from game results
-- Since transfermarkt-datasets doesn't have direct standings,
-- we derive them from game results.

-- Season performance: wins, draws, losses, goals for each club
WITH home_results AS (
    SELECT
        season,
        competition_id,
        home_club_id AS club_id,
        COUNT(*) AS matches,
        SUM(CASE WHEN home_club_goals > away_club_goals THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN home_club_goals = away_club_goals THEN 1 ELSE 0 END) AS draws,
        SUM(CASE WHEN home_club_goals < away_club_goals THEN 1 ELSE 0 END) AS losses,
        SUM(home_club_goals) AS goals_for,
        SUM(away_club_goals) AS goals_against
    FROM games
    WHERE home_club_goals IS NOT NULL AND away_club_goals IS NOT NULL
    GROUP BY season, competition_id, home_club_id
),
away_results AS (
    SELECT
        season,
        competition_id,
        away_club_id AS club_id,
        COUNT(*) AS matches,
        SUM(CASE WHEN away_club_goals > home_club_goals THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN away_club_goals = home_club_goals THEN 1 ELSE 0 END) AS draws,
        SUM(CASE WHEN away_club_goals < home_club_goals THEN 1 ELSE 0 END) AS losses,
        SUM(away_club_goals) AS goals_for,
        SUM(home_club_goals) AS goals_against
    FROM games
    WHERE home_club_goals IS NOT NULL AND away_club_goals IS NOT NULL
    GROUP BY season, competition_id, away_club_id
),
combined AS (
    SELECT
        COALESCE(h.season, a.season) AS season,
        COALESCE(h.competition_id, a.competition_id) AS competition_id,
        COALESCE(h.club_id, a.club_id) AS club_id,
        COALESCE(h.matches, 0) + COALESCE(a.matches, 0) AS played,
        COALESCE(h.wins, 0) + COALESCE(a.wins, 0) AS wins,
        COALESCE(h.draws, 0) + COALESCE(a.draws, 0) AS draws,
        COALESCE(h.losses, 0) + COALESCE(a.losses, 0) AS losses,
        COALESCE(h.goals_for, 0) + COALESCE(a.goals_for, 0) AS goals_for,
        COALESCE(h.goals_against, 0) + COALESCE(a.goals_against, 0) AS goals_against
    FROM home_results h
    FULL OUTER JOIN away_results a
        ON h.season = a.season 
        AND h.competition_id = a.competition_id 
        AND h.club_id = a.club_id
)
SELECT
    season,
    competition_id,
    club_id,
    c.name AS club_name,
    played,
    wins,
    draws,
    losses,
    (wins * 3 + draws) AS points,
    goals_for,
    goals_against,
    (goals_for - goals_against) AS goal_difference,
    RANK() OVER (
        PARTITION BY season, competition_id 
        ORDER BY (wins * 3 + draws) DESC, (goals_for - goals_against) DESC
    ) AS league_position
FROM combined
JOIN clubs c ON CAST(combined.club_id AS VARCHAR) = CAST(c.club_id AS VARCHAR)
ORDER BY season DESC, competition_id, league_position;

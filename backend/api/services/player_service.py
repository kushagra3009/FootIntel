"""
Service layer for Phase 4.1 — Player Intelligence, Cross-Season Comparison,
and Transfer Spell Valuation Lookup using parameterized DuckDB queries.
"""

from datetime import date, datetime
from typing import Any
import duckdb
from fastapi import HTTPException, status

from analysis.utils import game_season_to_transfer_season, transfer_season_to_game_season
from api.schemas import (
    PaginationMeta,
    PlayerCareerSummary,
    PlayerClubSpellRow,
    PlayerComparisonMetrics,
    PlayerComparisonRadarAxis,
    PlayerComparisonResponse,
    PlayerComparisonSide,
    PlayerDetailResponse,
    PlayerProfile,
    PlayerSearchItem,
    PlayerSearchResponse,
    PlayerSeasonStatsRow,
    PlayerTransferRow,
    PlayerTransferSpellsResponse,
    PlayerValuationPoint,
    TransferSpellCalculatorRow,
)

VALUATION_DISCLAIMER = (
    "Transfermarkt market values are crowdsourced estimated valuations, not actual club accounting "
    "book values, realized sale proceeds, or financial ROI. Wages, amortization, agent fees, "
    "sell-on clauses, and performance bonuses are not observed in this database."
)

UNAVAILABLE_METRICS_NOTE = (
    "Observed match metrics are strictly limited to DuckDB appearances records (appearances, "
    "goals, assists, minutes_played, yellow_cards, red_cards, and derived per-appearance rates "
    "from 2012–2025). Metrics not present in the database—such as xG, xA, shots, key passes, "
    "passing accuracy, tackles, saves, match ratings, and wages—are never estimated or fabricated."
)

SEASON_BOUNDARY_DEFINITION = (
    "Appearance performance metrics filter strictly by games.season = S. Season-aligned market "
    "valuations use the latest player_valuations entry inside [S-07-01, (S+1)-06-30] (falling back "
    "explicitly to the latest prior valuation <= (S+1)-06-30 when absent inside the window). "
    "Season transfer fees match transfers where transfer_season maps to S (or transfer_date falls "
    "within [S-07-01, (S+1)-06-30]), reported separately from prior career paid fees."
)


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _compute_age(dob_value: Any) -> int | None:
    if dob_value is None:
        return None
    dob = dob_value.date() if isinstance(dob_value, datetime) else dob_value
    if not isinstance(dob, date):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _fee_status(fee: float | None) -> str:
    if fee is None:
        return "undisclosed"
    if fee > 0:
        return "paid"
    return "free_or_loan"


def _season_label(season: int | None) -> str:
    if season is None:
        return "Career (All Recorded Seasons)"
    return game_season_to_transfer_season(season)


def _fetch_player_profile(con: duckdb.DuckDBPyConnection, player_id: int) -> PlayerProfile:
    row = con.execute(
        """
        SELECT
            p.player_id,
            p.name,
            p.first_name,
            p.last_name,
            p.country_of_citizenship,
            p.country_of_birth,
            p.city_of_birth,
            p.date_of_birth,
            p.position,
            p.sub_position,
            p.foot,
            p.height_in_cm,
            p.contract_expiration_date,
            p.current_club_id,
            p.current_club_name,
            p.current_club_domestic_competition_id,
            p.market_value_in_eur,
            p.highest_market_value_in_eur,
            lv.market_value_in_eur AS latest_val_eur,
            lv.val_date AS latest_val_date,
            p.last_season,
            p.image_url,
            p.url
        FROM players p
        LEFT JOIN (
            SELECT
                player_id,
                market_value_in_eur,
                date AS val_date,
                ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY date DESC) AS rn
            FROM player_valuations
            WHERE player_id = ?
        ) lv ON p.player_id = lv.player_id AND lv.rn = 1
        WHERE p.player_id = ?
        """,
        [player_id, player_id],
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player with player_id={player_id} was not found in DuckDB.",
        )

    return PlayerProfile(
        player_id=int(row[0]),
        name=row[1],
        first_name=row[2],
        last_name=row[3],
        country_of_citizenship=row[4],
        country_of_birth=row[5],
        city_of_birth=row[6],
        date_of_birth=_iso_date(row[7]),
        age=_compute_age(row[7]),
        position=row[8],
        sub_position=row[9],
        foot=row[10],
        height_in_cm=int(row[11]) if row[11] is not None else None,
        contract_expiration_date=_iso_date(row[12]),
        current_club_id=int(row[13]) if row[13] is not None else None,
        current_club_name=row[14],
        current_club_domestic_competition_id=row[15],
        market_value_in_eur=int(row[16]) if row[16] is not None else None,
        highest_market_value_in_eur=int(row[17]) if row[17] is not None else None,
        latest_valuation_in_eur=int(row[18]) if row[18] is not None else None,
        latest_valuation_date=_iso_date(row[19]),
        last_season=int(row[20]) if row[20] is not None else None,
        image_url=row[21],
        url=row[22],
    )


def search_players(
    con: duckdb.DuckDBPyConnection,
    q: str | None = None,
    position: str | None = None,
    nationality: str | None = None,
    min_appearances: int | None = None,
    sort_by: str = "market_value",
    limit: int = 20,
    offset: int = 0,
) -> PlayerSearchResponse:
    """Search players with parameterized filters and bounded pagination."""
    clauses: list[str] = []
    params: list[Any] = []

    if q and q.strip():
        clauses.append("p.name ILIKE ?")
        params.append(f"%{q.strip()}%")
    if position and position.strip():
        clauses.append("p.position = ?")
        params.append(position.strip())
    if nationality and nationality.strip():
        clauses.append("p.country_of_citizenship ILIKE ?")
        params.append(f"%{nationality.strip()}%")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sort_map = {
        "market_value": "COALESCE(p.market_value_in_eur, -1) DESC, COALESCE(p.highest_market_value_in_eur, -1) DESC, p.name ASC",
        "highest_market_value": "COALESCE(p.highest_market_value_in_eur, -1) DESC, COALESCE(p.market_value_in_eur, -1) DESC, p.name ASC",
        "name": "p.name ASC, p.player_id ASC",
        "last_season": "COALESCE(p.last_season, -1) DESC, COALESCE(p.market_value_in_eur, -1) DESC, p.name ASC",
        "appearances": "COALESCE(app.appearance_count, 0) DESC, COALESCE(p.market_value_in_eur, -1) DESC, p.name ASC",
    }
    order_sql = sort_map.get(sort_by, sort_map["market_value"])

    needs_app_join_for_filter_or_sort = min_appearances is not None or sort_by == "appearances"

    if needs_app_join_for_filter_or_sort:
        having_clause = ""
        having_params: list[Any] = []
        if min_appearances is not None:
            having_clause = "AND COALESCE(app.appearance_count, 0) >= ?"
            having_params.append(min_appearances)

        base_from = f"""
            FROM players p
            LEFT JOIN (
                SELECT
                    player_id,
                    COUNT(*) AS appearance_count,
                    COALESCE(SUM(goals), 0) AS total_goals,
                    COALESCE(SUM(assists), 0) AS total_assists
                FROM appearances
                GROUP BY player_id
            ) app ON p.player_id = app.player_id
            {where_sql if where_sql else "WHERE 1=1"}
            {having_clause}
        """
        full_params = [*params, *having_params]
        total_row = con.execute(f"SELECT COUNT(*) {base_from}", full_params).fetchone()
        total = int(total_row[0]) if total_row else 0

        rows = con.execute(
            f"""
            SELECT
                p.player_id, p.name, p.country_of_citizenship, p.date_of_birth,
                p.position, p.sub_position, p.current_club_id, p.current_club_name,
                p.current_club_domestic_competition_id, p.market_value_in_eur,
                p.highest_market_value_in_eur, p.last_season,
                COALESCE(app.appearance_count, 0),
                COALESCE(app.total_goals, 0),
                COALESCE(app.total_assists, 0),
                p.image_url
            {base_from}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*full_params, limit, offset],
        ).fetchall()
    else:
        total_row = con.execute(f"SELECT COUNT(*) FROM players p {where_sql}", params).fetchone()
        total = int(total_row[0]) if total_row else 0

        rows = con.execute(
            f"""
            WITH page_players AS (
                SELECT
                    p.player_id, p.name, p.country_of_citizenship, p.date_of_birth,
                    p.position, p.sub_position, p.current_club_id, p.current_club_name,
                    p.current_club_domestic_competition_id, p.market_value_in_eur,
                    p.highest_market_value_in_eur, p.last_season, p.image_url
                FROM players p
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
            ),
            page_apps AS (
                SELECT
                    a.player_id,
                    COUNT(*) AS appearance_count,
                    COALESCE(SUM(a.goals), 0) AS total_goals,
                    COALESCE(SUM(a.assists), 0) AS total_assists
                FROM appearances a
                JOIN page_players pp ON a.player_id = pp.player_id
                GROUP BY a.player_id
            )
            SELECT
                pp.player_id, pp.name, pp.country_of_citizenship, pp.date_of_birth,
                pp.position, pp.sub_position, pp.current_club_id, pp.current_club_name,
                pp.current_club_domestic_competition_id, pp.market_value_in_eur,
                pp.highest_market_value_in_eur, pp.last_season,
                COALESCE(pa.appearance_count, 0),
                COALESCE(pa.total_goals, 0),
                COALESCE(pa.total_assists, 0),
                pp.image_url
            FROM page_players pp
            LEFT JOIN page_apps pa ON pp.player_id = pa.player_id
            ORDER BY {order_sql.replace('p.', 'pp.')}
            """,
            [*params, limit, offset],
        ).fetchall()

    positions = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT position FROM players WHERE position IS NOT NULL ORDER BY position"
        ).fetchall()
    ]

    items = [
        PlayerSearchItem(
            player_id=int(r[0]),
            name=r[1],
            country_of_citizenship=r[2],
            date_of_birth=_iso_date(r[3]),
            age=_compute_age(r[3]),
            position=r[4],
            sub_position=r[5],
            current_club_id=int(r[6]) if r[6] is not None else None,
            current_club_name=r[7],
            current_club_domestic_competition_id=r[8],
            market_value_in_eur=int(r[9]) if r[9] is not None else None,
            highest_market_value_in_eur=int(r[10]) if r[10] is not None else None,
            last_season=int(r[11]) if r[11] is not None else None,
            appearance_count=int(r[12]),
            total_goals=int(r[13]),
            total_assists=int(r[14]),
            image_url=r[15],
        )
        for r in rows
    ]

    return PlayerSearchResponse(
        players=items,
        available_positions=positions,
        pagination=PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            returned=len(items),
        ),
    )


def get_player_detail(con: duckdb.DuckDBPyConnection, player_id: int) -> PlayerDetailResponse:
    """Return full profile, season-aligned stats, valuation history, transfers, and timeline."""
    profile = _fetch_player_profile(con, player_id)

    season_rows = con.execute(
        """
        SELECT
            g.season,
            COUNT(*) AS appearances,
            COALESCE(SUM(a.goals), 0) AS goals,
            COALESCE(SUM(a.assists), 0) AS assists,
            COALESCE(SUM(a.minutes_played), 0) AS minutes_played,
            COALESCE(SUM(a.yellow_cards), 0) AS yellow_cards,
            COALESCE(SUM(a.red_cards), 0) AS red_cards,
            LIST(DISTINCT COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))
                 ORDER BY COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))) AS clubs,
            LIST(DISTINCT a.competition_id ORDER BY a.competition_id) AS competitions
        FROM appearances a
        JOIN games g ON a.game_id = g.game_id
        LEFT JOIN clubs c ON a.player_club_id = c.club_id
        WHERE a.player_id = ?
        GROUP BY g.season
        ORDER BY g.season ASC
        """,
        [player_id],
    ).fetchall()

    season_stats: list[PlayerSeasonStatsRow] = []
    tot_apps = tot_goals = tot_assists = tot_mins = tot_yellow = tot_red = 0
    for r in season_rows:
        s = int(r[0])
        apps = int(r[1])
        goals = int(r[2])
        assists = int(r[3])
        mins = int(r[4])
        yellow = int(r[5])
        red = int(r[6])
        tot_apps += apps
        tot_goals += goals
        tot_assists += assists
        tot_mins += mins
        tot_yellow += yellow
        tot_red += red
        season_stats.append(
            PlayerSeasonStatsRow(
                season=s,
                season_label=_season_label(s),
                appearances=apps,
                goals=goals,
                assists=assists,
                minutes_played=mins,
                yellow_cards=yellow,
                red_cards=red,
                goals_per_appearance=round(goals / apps, 4) if apps > 0 else None,
                assists_per_appearance=round(assists / apps, 4) if apps > 0 else None,
                clubs=[x for x in (r[7] or []) if x],
                competitions=[x for x in (r[8] or []) if x],
            )
        )

    val_rows = con.execute(
        """
        SELECT date, market_value_in_eur, current_club_id, current_club_name, player_club_domestic_competition_id
        FROM player_valuations
        WHERE player_id = ?
        ORDER BY date ASC
        """,
        [player_id],
    ).fetchall()
    valuations = [
        PlayerValuationPoint(
            date=_iso_date(r[0]) or "",
            market_value_in_eur=int(r[1]),
            current_club_id=int(r[2]) if r[2] is not None else None,
            current_club_name=r[3],
            competition_id=r[4],
        )
        for r in val_rows
    ]

    today = date.today()
    tr_rows = con.execute(
        """
        SELECT
            transfer_date,
            transfer_season,
            from_club_id,
            from_club_name,
            to_club_id,
            to_club_name,
            transfer_fee,
            market_value_in_eur
        FROM transfers
        WHERE player_id = ?
        ORDER BY transfer_date DESC NULLS LAST
        """,
        [player_id],
    ).fetchall()
    transfers: list[PlayerTransferRow] = []
    for r in tr_rows:
        tdate = r[0]
        tseason = r[1]
        fee = float(r[6]) if r[6] is not None else None
        mv = float(r[7]) if r[7] is not None else None
        transfers.append(
            PlayerTransferRow(
                transfer_date=_iso_date(tdate),
                transfer_season=tseason,
                game_season=transfer_season_to_game_season(tseason) if tseason else None,
                from_club_id=int(r[2]) if r[2] is not None else None,
                from_club_name=r[3],
                to_club_id=int(r[4]) if r[4] is not None else None,
                to_club_name=r[5],
                transfer_fee=fee,
                fee_status=_fee_status(fee),
                market_value_in_eur=mv,
                is_future_scheduled=bool(tdate is not None and tdate > today),
            )
        )

    # Club career timeline built from appearances (exact game seasons) enriched with transfer clubs
    club_app_rows = con.execute(
        """
        SELECT
            a.player_club_id,
            COALESCE(MAX(c.name), 'Club #' || CAST(a.player_club_id AS VARCHAR)) AS club_name,
            MAX(c.domestic_competition_id) AS competition_id,
            MIN(g.season) AS first_season,
            MAX(g.season) AS last_season,
            COUNT(*) AS appearances,
            COALESCE(SUM(a.goals), 0) AS goals,
            COALESCE(SUM(a.assists), 0) AS assists,
            COALESCE(SUM(a.minutes_played), 0) AS minutes_played
        FROM appearances a
        JOIN games g ON a.game_id = g.game_id
        LEFT JOIN clubs c ON a.player_club_id = c.club_id
        WHERE a.player_id = ?
        GROUP BY a.player_club_id
        ORDER BY first_season ASC, last_season ASC
        """,
        [player_id],
    ).fetchall()

    transfer_club_ids = {t.to_club_id for t in transfers if t.to_club_id is not None} | {
        t.from_club_id for t in transfers if t.from_club_id is not None
    }
    seen_app_club_ids: set[int] = set()
    club_timeline: list[PlayerClubSpellRow] = []

    for r in club_app_rows:
        cid = int(r[0]) if r[0] is not None else None
        if cid is not None:
            seen_app_club_ids.add(cid)
        fs, ls = int(r[3]), int(r[4])
        span = _season_label(fs) if fs == ls else f"{_season_label(fs)} – {_season_label(ls)}"
        club_timeline.append(
            PlayerClubSpellRow(
                club_id=cid,
                club_name=r[1],
                competition_id=r[2],
                first_season=fs,
                last_season=ls,
                season_span=span,
                appearances=int(r[5]),
                goals=int(r[6]),
                assists=int(r[7]),
                minutes_played=int(r[8]),
                source="both" if (cid is not None and cid in transfer_club_ids) else "appearances",
            )
        )

    # Append destination clubs from transfers not already represented in appearances (e.g. youth/pre-2012/unplayed loans)
    added_transfer_clubs: set[tuple[int | None, str]] = set()
    for t in reversed(transfers):  # chronological order
        if not t.to_club_name:
            continue
        if t.to_club_id is not None and t.to_club_id in seen_app_club_ids:
            continue
        key = (t.to_club_id, t.to_club_name)
        if key in added_transfer_clubs:
            continue
        added_transfer_clubs.add(key)
        gs = t.game_season
        club_timeline.append(
            PlayerClubSpellRow(
                club_id=t.to_club_id,
                club_name=t.to_club_name,
                competition_id=None,
                first_season=gs,
                last_season=gs,
                season_span=t.transfer_season or (t.transfer_date or "Recorded transfer"),
                appearances=0,
                goals=0,
                assists=0,
                minutes_played=0,
                source="transfers",
            )
        )

    career_summary = PlayerCareerSummary(
        has_appearance_data=tot_apps > 0,
        has_valuation_data=len(valuations) > 0,
        has_transfer_data=len(transfers) > 0,
        appearances=tot_apps,
        goals=tot_goals,
        assists=tot_assists,
        minutes_played=tot_mins,
        yellow_cards=tot_yellow,
        red_cards=tot_red,
        goals_per_appearance=round(tot_goals / tot_apps, 4) if tot_apps > 0 else None,
        assists_per_appearance=round(tot_assists / tot_apps, 4) if tot_apps > 0 else None,
        seasons_with_appearances=len(season_stats),
        first_appearance_season=season_stats[0].season if season_stats else None,
        last_appearance_season=season_stats[-1].season if season_stats else None,
        unavailable_metrics_note=UNAVAILABLE_METRICS_NOTE,
    )

    return PlayerDetailResponse(
        profile=profile,
        career_summary=career_summary,
        season_stats=season_stats,
        market_value_history=valuations,
        transfer_history=transfers,
        club_timeline=club_timeline,
        valuation_disclaimer=VALUATION_DISCLAIMER,
    )


def _compute_side_comparison(
    con: duckdb.DuckDBPyConnection,
    player_id: int,
    season: int | None,
) -> PlayerComparisonSide:
    profile = _fetch_player_profile(con, player_id)

    seasons_rows = con.execute(
        """
        SELECT DISTINCT g.season
        FROM appearances a
        JOIN games g ON a.game_id = g.game_id
        WHERE a.player_id = ?
        ORDER BY g.season DESC
        """,
        [player_id],
    ).fetchall()
    available_seasons = [int(r[0]) for r in seasons_rows]

    # 1. Performance metrics scoped strictly by games.season when provided
    if season is not None:
        perf_row = con.execute(
            """
            SELECT
                COUNT(*) AS appearances,
                COALESCE(SUM(a.goals), 0) AS goals,
                COALESCE(SUM(a.assists), 0) AS assists,
                COALESCE(SUM(a.minutes_played), 0) AS minutes_played,
                COALESCE(SUM(a.yellow_cards), 0) AS yellow_cards,
                COALESCE(SUM(a.red_cards), 0) AS red_cards,
                LIST(DISTINCT COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))
                     ORDER BY COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))) AS clubs,
                LIST(DISTINCT a.competition_id ORDER BY a.competition_id) AS competitions
            FROM appearances a
            JOIN games g ON a.game_id = g.game_id
            LEFT JOIN clubs c ON a.player_club_id = c.club_id
            WHERE a.player_id = ? AND g.season = ?
            """,
            [player_id, season],
        ).fetchone()
    else:
        perf_row = con.execute(
            """
            SELECT
                COUNT(*) AS appearances,
                COALESCE(SUM(a.goals), 0) AS goals,
                COALESCE(SUM(a.assists), 0) AS assists,
                COALESCE(SUM(a.minutes_played), 0) AS minutes_played,
                COALESCE(SUM(a.yellow_cards), 0) AS yellow_cards,
                COALESCE(SUM(a.red_cards), 0) AS red_cards,
                LIST(DISTINCT COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))
                     ORDER BY COALESCE(c.name, 'Club #' || CAST(a.player_club_id AS VARCHAR))) AS clubs,
                LIST(DISTINCT a.competition_id ORDER BY a.competition_id) AS competitions
            FROM appearances a
            JOIN games g ON a.game_id = g.game_id
            LEFT JOIN clubs c ON a.player_club_id = c.club_id
            WHERE a.player_id = ?
            """,
            [player_id],
        ).fetchone()

    apps = int(perf_row[0]) if perf_row else 0
    goals = int(perf_row[1]) if perf_row else 0
    assists = int(perf_row[2]) if perf_row else 0
    mins = int(perf_row[3]) if perf_row else 0
    yellow = int(perf_row[4]) if perf_row else 0
    red = int(perf_row[5]) if perf_row else 0
    clubs = [x for x in (perf_row[6] or []) if x] if apps > 0 and perf_row else []
    comps = [x for x in (perf_row[7] or []) if x] if apps > 0 and perf_row else []

    # 2. Season-bounded Market Valuation & Transfer Fees
    if season is not None:
        win_start = date(season, 7, 1)
        win_end = date(season + 1, 6, 30)
        ts_label = game_season_to_transfer_season(season)

        in_win = con.execute(
            """
            SELECT market_value_in_eur, date
            FROM player_valuations
            WHERE player_id = ? AND date >= ? AND date <= ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [player_id, win_start, win_end],
        ).fetchone()

        if in_win is not None:
            mv_eur = int(in_win[0])
            mv_date = _iso_date(in_win[1])
            mv_note = f"Latest within {ts_label} season window ({win_start} to {win_end})"
        else:
            prior = con.execute(
                """
                SELECT market_value_in_eur, date
                FROM player_valuations
                WHERE player_id = ? AND date <= ?
                ORDER BY date DESC
                LIMIT 1
                """,
                [player_id, win_end],
            ).fetchone()
            if prior is not None:
                mv_eur = int(prior[0])
                mv_date = _iso_date(prior[1])
                mv_note = f"No valuation inside {ts_label}; carried forward from {mv_date} (<= {win_end})"
            else:
                mv_eur = None
                mv_date = None
                mv_note = f"No valuation recorded on or before {win_end}"

        # Transfers in season S (matching transfer_season == ts_label OR date in window when ts NULL)
        tr_season_rows = con.execute(
            """
            SELECT transfer_fee, from_club_name, to_club_name, transfer_date, transfer_season
            FROM transfers
            WHERE player_id = ?
              AND (transfer_season = ? OR (transfer_season IS NULL AND transfer_date >= ? AND transfer_date <= ?))
            ORDER BY COALESCE(transfer_fee, -1) DESC, transfer_date DESC
            """,
            [player_id, ts_label, win_start, win_end],
        ).fetchall()

        if tr_season_rows:
            chosen = tr_season_rows[0]
            season_fee = float(chosen[0]) if chosen[0] is not None else None
            season_fee_status = _fee_status(season_fee)
            season_tr_desc = f"{chosen[1] or 'Unknown'} -> {chosen[2] or 'Unknown'} ({chosen[4] or _iso_date(chosen[3])})"
        else:
            season_fee = None
            season_fee_status = "no_transfer_in_season"
            season_tr_desc = f"No transfer recorded in {ts_label}"

        prior_paid = con.execute(
            """
            SELECT transfer_fee, transfer_season
            FROM transfers
            WHERE player_id = ?
              AND transfer_fee > 0
              AND (transfer_date IS NULL OR transfer_date <= ?)
            ORDER BY transfer_date DESC NULLS LAST
            LIMIT 1
            """,
            [player_id, win_end],
        ).fetchone()
    else:
        latest_val = con.execute(
            """
            SELECT market_value_in_eur, date
            FROM player_valuations
            WHERE player_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            [player_id],
        ).fetchone()
        if latest_val is not None:
            mv_eur = int(latest_val[0])
            mv_date = _iso_date(latest_val[1])
            mv_note = f"Latest career valuation recorded on {mv_date}"
        else:
            mv_eur = profile.market_value_in_eur
            mv_date = None
            mv_note = (
                "From players.market_value_in_eur snapshot (no dated valuation series)"
                if mv_eur is not None
                else "No valuation recorded in DuckDB"
            )

        max_paid = con.execute(
            """
            SELECT transfer_fee, from_club_name, to_club_name, transfer_season
            FROM transfers
            WHERE player_id = ? AND transfer_fee > 0
            ORDER BY transfer_fee DESC, transfer_date DESC NULLS LAST
            LIMIT 1
            """,
            [player_id],
        ).fetchone()
        if max_paid is not None:
            season_fee = float(max_paid[0])
            season_fee_status = "paid"
            season_tr_desc = f"Peak recorded career fee: {max_paid[1] or 'Unknown'} -> {max_paid[2] or 'Unknown'} ({max_paid[3] or ''})"
        else:
            season_fee = None
            season_fee_status = "no_paid_transfer_recorded"
            season_tr_desc = "No paid transfer fee (> €0) recorded in career history"

        prior_paid = con.execute(
            """
            SELECT transfer_fee, transfer_season
            FROM transfers
            WHERE player_id = ? AND transfer_fee > 0
            ORDER BY transfer_date DESC NULLS LAST
            LIMIT 1
            """,
            [player_id],
        ).fetchone()

    metrics = PlayerComparisonMetrics(
        scope_type="season" if season is not None else "career",
        selected_season=season,
        selected_season_label=_season_label(season),
        has_appearance_data=apps > 0,
        appearances=apps,
        goals=goals,
        assists=assists,
        minutes_played=mins,
        yellow_cards=yellow,
        red_cards=red,
        goals_per_appearance=round(goals / apps, 4) if apps > 0 else None,
        assists_per_appearance=round(assists / apps, 4) if apps > 0 else None,
        clubs_in_scope=clubs,
        competitions_in_scope=comps,
        market_value_in_eur=mv_eur,
        market_value_date=mv_date,
        market_value_boundary_note=mv_note,
        season_transfer_fee_eur=season_fee,
        season_transfer_fee_status=season_fee_status,
        season_transfer_description=season_tr_desc,
        latest_paid_transfer_fee_eur=float(prior_paid[0]) if prior_paid is not None else None,
        latest_paid_transfer_season=prior_paid[1] if prior_paid is not None else None,
    )

    return PlayerComparisonSide(
        profile=profile,
        available_seasons=available_seasons,
        metrics=metrics,
    )


def compare_players(
    con: duckdb.DuckDBPyConnection,
    player_a_id: int,
    player_b_id: int,
    season_a: int | None = None,
    season_b: int | None = None,
) -> PlayerComparisonResponse:
    """Compare two players (same season, cross-season, or same player across seasons)."""
    side_a = _compute_side_comparison(con, player_a_id, season_a)
    side_b = _compute_side_comparison(con, player_b_id, season_b)

    if season_a is None and season_b is None:
        mode = "career"
    elif player_a_id == player_b_id:
        mode = "same_player_cross_season"
    elif season_a is not None and season_a == season_b:
        mode = "same_season"
    else:
        mode = "different_seasons"

    radar_supported = side_a.metrics.has_appearance_data and side_b.metrics.has_appearance_data
    radar_reason: str | None = None
    radar_axes: list[PlayerComparisonRadarAxis] = []

    if not radar_supported:
        missing_names = []
        if not side_a.metrics.has_appearance_data:
            missing_names.append(f"{side_a.profile.name} ({side_a.metrics.selected_season_label})")
        if not side_b.metrics.has_appearance_data:
            missing_names.append(f"{side_b.profile.name} ({side_b.metrics.selected_season_label})")
        radar_reason = (
            "Radar chart disabled because appearance statistics are empty for: "
            + ", ".join(missing_names)
            + "."
        )
    else:
        raw_pairs = [
            ("Appearances", "matches", float(side_a.metrics.appearances), float(side_b.metrics.appearances)),
            ("Minutes Played", "mins", float(side_a.metrics.minutes_played), float(side_b.metrics.minutes_played)),
            ("Goals", "goals", float(side_a.metrics.goals), float(side_b.metrics.goals)),
            ("Assists", "assists", float(side_a.metrics.assists), float(side_b.metrics.assists)),
            (
                "Goals / App",
                "ratio",
                float(side_a.metrics.goals_per_appearance or 0.0),
                float(side_b.metrics.goals_per_appearance or 0.0),
            ),
            (
                "Assists / App",
                "ratio",
                float(side_a.metrics.assists_per_appearance or 0.0),
                float(side_b.metrics.assists_per_appearance or 0.0),
            ),
        ]
        for label, unit, raw_a, raw_b in raw_pairs:
            denom = max(raw_a, raw_b)
            score_a = round((raw_a / denom) * 100.0, 1) if denom > 0 else 0.0
            score_b = round((raw_b / denom) * 100.0, 1) if denom > 0 else 0.0
            radar_axes.append(
                PlayerComparisonRadarAxis(
                    metric=label,
                    unit=unit,
                    player_a_raw=raw_a,
                    player_b_raw=raw_b,
                    player_a_score=score_a,
                    player_b_score=score_b,
                )
            )

    return PlayerComparisonResponse(
        comparison_mode=mode,
        season_boundary_definition=SEASON_BOUNDARY_DEFINITION,
        player_a=side_a,
        player_b=side_b,
        radar_supported=radar_supported,
        radar_unavailable_reason=radar_reason,
        radar_axes=radar_axes,
        unavailable_metrics_note=UNAVAILABLE_METRICS_NOTE,
        valuation_disclaimer=VALUATION_DISCLAIMER,
    )


def get_player_transfer_spells(
    con: duckdb.DuckDBPyConnection,
    player_id: int,
) -> PlayerTransferSpellsResponse:
    """Return transfer spells with arrival valuation, spell-bounded peak/latest MV, and MV/Fee multiples."""
    profile = _fetch_player_profile(con, player_id)

    tr_rows = con.execute(
        """
        SELECT
            t.transfer_date,
            t.transfer_season,
            t.from_club_name,
            t.to_club_id,
            t.to_club_name,
            c.domestic_competition_id,
            t.transfer_fee,
            t.market_value_in_eur
        FROM transfers t
        LEFT JOIN clubs c ON t.to_club_id = c.club_id
        WHERE t.player_id = ?
        ORDER BY t.transfer_date ASC NULLS LAST
        """,
        [player_id],
    ).fetchall()

    val_rows = con.execute(
        """
        SELECT date, market_value_in_eur
        FROM player_valuations
        WHERE player_id = ?
        ORDER BY date ASC
        """,
        [player_id],
    ).fetchall()

    dated_transfers = [r for r in tr_rows if r[0] is not None]
    undated_transfers = [r for r in tr_rows if r[0] is None]
    ordered = dated_transfers + undated_transfers

    spells: list[TransferSpellCalculatorRow] = []
    for idx, r in enumerate(ordered):
        tdate: date | None = r[0]
        tseason: str | None = r[1]
        from_club: str | None = r[2]
        to_club_id: int | None = int(r[3]) if r[3] is not None else None
        to_club_name: str | None = r[4]
        to_league_id: str | None = r[5]
        fee: float | None = float(r[6]) if r[6] is not None else None
        arrival_mv_raw: float | None = float(r[7]) if r[7] is not None else None

        next_date: date | None = None
        if tdate is not None:
            for nxt in ordered[idx + 1 :]:
                if nxt[0] is not None and nxt[0] > tdate:
                    next_date = nxt[0]
                    break

        # Arrival MV source
        mv_arrival: float | None = arrival_mv_raw
        mv_arrival_src: str | None = "transfers.market_value_in_eur" if arrival_mv_raw is not None else None
        if mv_arrival is None and tdate is not None:
            prior_vals = [v for v in val_rows if v[0] <= tdate]
            if prior_vals:
                mv_arrival = float(prior_vals[-1][1])
                mv_arrival_src = f"player_valuations ({_iso_date(prior_vals[-1][0])})"

        # Spell-bounded valuations inside [transfer_date, next_transfer_date)
        spell_vals: list[tuple[date, int]] = []
        if tdate is not None:
            for vdate, vval in val_rows:
                if vdate >= tdate and (next_date is None or vdate < next_date):
                    spell_vals.append((vdate, int(vval)))

        peak_mv = float(max(v[1] for v in spell_vals)) if spell_vals else None
        latest_mv = float(spell_vals[-1][1]) if spell_vals else None
        last_val_date = _iso_date(spell_vals[-1][0]) if spell_vals else None

        est_peak_gain = est_peak_pct = peak_mult = est_latest_gain = latest_mult = None
        if fee is not None and fee > 0:
            if peak_mv is not None:
                est_peak_gain = peak_mv - fee
                est_peak_pct = round(((peak_mv - fee) / fee) * 100.0, 2)
                peak_mult = round(peak_mv / fee, 4)
            if latest_mv is not None:
                est_latest_gain = latest_mv - fee
                latest_mult = round(latest_mv / fee, 4)

        spells.append(
            TransferSpellCalculatorRow(
                spell_index=idx + 1,
                transfer_date=_iso_date(tdate),
                next_transfer_date=_iso_date(next_date),
                transfer_season=tseason,
                game_season=transfer_season_to_game_season(tseason) if tseason else None,
                from_club_name=from_club,
                to_club_id=to_club_id,
                to_club_name=to_club_name,
                to_league_id=to_league_id,
                transfer_fee=fee,
                fee_status=_fee_status(fee),
                mv_at_arrival=mv_arrival,
                mv_at_arrival_source=mv_arrival_src,
                peak_mv=peak_mv,
                latest_mv_at_club=latest_mv,
                valuation_count=len(spell_vals),
                last_valuation_date=last_val_date,
                est_peak_mv_gain=est_peak_gain,
                est_peak_mv_gain_pct=est_peak_pct,
                peak_mv_to_fee_multiple=peak_mult,
                est_latest_mv_gain=est_latest_gain,
                latest_mv_to_fee_multiple=latest_mult,
            )
        )

    # Show newest spells first for immediate relevance in Mode A UI
    spells.reverse()

    return PlayerTransferSpellsResponse(
        profile=profile,
        spells=spells,
        methodology_note=(
            "Spell valuations are strictly bounded from transfer_date up to (but excluding) the next "
            "chronological transfer_date. Estimated MV gain and MV/Fee multiples are computed only for "
            "paid transfers (transfer_fee > €0)."
        ),
        valuation_disclaimer=VALUATION_DISCLAIMER,
    )

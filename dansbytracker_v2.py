#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import csv
import io
import os
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# -------------------------
# CONFIG
# -------------------------
HTTP_TIMEOUT = 30

TEAM_ID_CUBS = 112
SWANSON_MLBAM_ID = 621020

EARLIEST_SEND_DATE = date(2026, 2, 20)
REGULAR_SEASON_START = date(2026, 3, 26)  # Rolling stats reset after this date

SEND_LOOKBACK_DAYS = 14
ROLLING_LOOKBACK_DAYS = 60

RECIPIENTS = [
    "robertjsherman1@gmail.com",
    "coreyolangreen@gmail.com",
    "jtdowning@gmail.com",
]

TEST_MODE = os.environ.get("TEST_MODE", "0").strip().lower() in ("1", "true", "yes")
FORCE_TEST_EMAIL = os.environ.get("FORCE_TEST_EMAIL", "0").strip().lower() in ("1", "true", "yes")
TEST_TO_EMAILS = [e.strip() for e in os.environ.get("TEST_TO_EMAILS", "").split(",") if e.strip()]
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()

DB_PATH = os.environ.get("DANSBYTRACKER_DB_PATH", "swanson_digest.sqlite").strip()

SAVANT_OAA_CSV_URL = os.environ.get("SAVANT_OAA_CSV_URL", "").strip()
SAVANT_FRV_CSV_URL = os.environ.get("SAVANT_FRV_CSV_URL", "").strip()

DUNSTON_CAREER_RISP_AVG = ".269"

SCHEDULE_QUERY_FALLBACKS: List[dict] = [
    {"sportId": 1,   "gameType": "S"},
    {"sportId": 1,   "gameType": "E"},
    {"sportId": 114, "gameType": None},
    {"sportId": 1,   "gameType": None},
    {"sportId": 1,   "gameType": "R"},
]

DANSBY_ACCOLADES = [
    "Elite hands. Elite footwork. Elite instincts.",
    "Another day, another clinic at shortstop.",
    "Defense that changes games.",
    "Quietly putting together a pro's pro season.",
    "The glove is always on time.",
    "One of the steadiest shortstops in the league.",
    "Turns routine into art.",
    "Every rep looks the same: clean and composed.",
    "Makes the tough plays look inevitable.",
    "Even on a 'quiet' night, the fundamentals are loud.",
]

# -------------------------
# UTIL
# -------------------------
def escape_html(s: str) -> str:
    s = "" if s is None else str(s)
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;")

def safe_int(x, default=0) -> int:
    try:
        return default if (x is None or x == "") else int(x)
    except Exception:
        return default

def safe_float(x, default=0.0) -> float:
    try:
        return default if (x is None or x == "") else float(x)
    except Exception:
        return default

def fmt_avg(x: float) -> str:
    try:
        return f"{x:.3f}".replace("0.", ".")
    except Exception:
        return ".000"

def fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()

def log(msg: str) -> None:
    try:
        with open("dansbytracker.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")
    except Exception:
        pass

# -------------------------
# DB
# -------------------------
def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.cursor().execute("CREATE TABLE IF NOT EXISTS sent_games (gamePk INTEGER PRIMARY KEY, sent_at TEXT)")
        conn.commit()
    finally:
        conn.close()

def was_sent(game_pk: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.cursor().execute("SELECT 1 FROM sent_games WHERE gamePk=?", (game_pk,)).fetchone() is not None
    finally:
        conn.close()

def mark_sent(game_pk: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.cursor().execute(
            "INSERT OR REPLACE INTO sent_games (gamePk, sent_at) VALUES (?, ?)",
            (game_pk, datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
    finally:
        conn.close()

# -------------------------
# Season phase
# -------------------------
def is_spring_training(today: date = None) -> bool:
    return (today or date.today()) < REGULAR_SEASON_START

# -------------------------
# MLB schedule / boxscore
# -------------------------
def fetch_team_schedule_with_fallbacks(team_id: int, start: date, end: date) -> List[dict]:
    padded_end = end + timedelta(days=1)
    seen_pks: set = set()
    last_err = None
    for q in SCHEDULE_QUERY_FALLBACKS:
        try:
            url = (
                f"https://statsapi.mlb.com/api/v1/schedule"
                f"?sportId={q['sportId']}&teamId={team_id}"
                f"&startDate={start.isoformat()}&endDate={padded_end.isoformat()}"
            )
            if q.get("gameType"):
                url += f"&gameType={q['gameType']}"
            log(f"Schedule: {url}")
            data = fetch_json(url)
            games = [g for d in data.get("dates", []) for g in d.get("games", [])
                     if g.get("gamePk") and g["gamePk"] not in seen_pks]
            for g in games:
                seen_pks.add(g["gamePk"])
            if games:
                games.sort(key=lambda x: x.get("gameDate", ""), reverse=True)
                log(f"  -> {len(games)} game(s)")
                return games
            log(f"  -> 0 games")
        except Exception as e:
            last_err = e
            log(f"  -> error: {e}")
    if last_err:
        log(f"All fallbacks exhausted: {last_err}")
    return []

def game_is_final(g: dict) -> bool:
    state = (g.get("status") or {}).get("detailedState", "")
    abstract = (g.get("status") or {}).get("abstractGameState", "")
    return state in ("Final", "Game Over") or state.startswith("Completed") or abstract == "Final"

def opponent_for_team(game: dict, team_name: str = "Chicago Cubs") -> str:
    teams = game.get("teams") or {}
    away = ((teams.get("away") or {}).get("team") or {}).get("name", "")
    home = ((teams.get("home") or {}).get("team") or {}).get("name", "")
    return (away if home == team_name else home) or "Unknown"

def fetch_boxscore(game_pk: int) -> dict:
    return fetch_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")

def find_player_in_boxscore(box: dict, mlbam_id: int) -> Optional[Tuple[dict, dict]]:
    for side in ("home", "away"):
        for _pid, pdata in ((box.get("teams") or {}).get(side, {}).get("players", {}) or {}).items():
            if safe_int(((pdata.get("person") or {}).get("id"))) == mlbam_id:
                stats = pdata.get("stats") or {}
                return stats.get("batting") or {}, stats.get("fielding") or {}
    log(f"Player {mlbam_id} not in boxscore.")
    return None

@dataclass
class GameRow:
    gamePk: int
    game_date: str
    opponent: str
    batting: dict
    fielding: dict

def load_recent_games_with_swanson(today: date, lookback_days: int) -> List[GameRow]:
    games = fetch_team_schedule_with_fallbacks(TEAM_ID_CUBS, today - timedelta(days=lookback_days), today)
    rows: List[GameRow] = []
    for g in games:
        if not game_is_final(g):
            continue
        game_pk = g.get("gamePk")
        if not game_pk:
            continue
        try:
            box = fetch_boxscore(int(game_pk))
        except Exception as e:
            log(f"Boxscore error {game_pk}: {e}")
            continue
        found = find_player_in_boxscore(box, SWANSON_MLBAM_ID)
        if not found:
            continue
        batting, fielding = found
        rows.append(GameRow(
            gamePk=int(game_pk),
            game_date=(g.get("officialDate") or (g.get("gameDate") or "")[:10] or ""),
            opponent=opponent_for_team(g),
            batting=batting,
            fielding=fielding,
        ))
    log(f"load_recent_games: {len(rows)} game(s) with Swanson.")
    return rows

def pick_unsent_anchor_game(today: date, lookback_days: int) -> Optional[GameRow]:
    for r in load_recent_games_with_swanson(today, lookback_days):
        try:
            gd = date.fromisoformat((r.game_date or "")[:10])
        except Exception:
            continue
        if gd < today and not was_sent(r.gamePk):
            return r
    return None

# -------------------------
# Spring Training cumulative stats
# Three strategies tried in order — first success wins:
#   1. statsapi per-player hydrate (targeted, no scanning)
#   2. bdfed leaderboard scan (confirmed field names from mlb_scraper source)
#   3. statsapi /people/{id}/stats with gameType=S
# -------------------------
@dataclass
class STCumulativeStats:
    games: int = 0
    atBats: int = 0
    hits: int = 0
    homeRuns: int = 0
    rbi: int = 0
    baseOnBalls: int = 0
    strikeOuts: int = 0
    doubles: int = 0
    triples: int = 0
    hitByPitch: int = 0
    sacFlies: int = 0
    avg: str = "N/A"
    obp: str = "N/A"
    slg: str = "N/A"
    ops: str = "N/A"
    found: bool = False


def _derive_rates(result: "STCumulativeStats", stat_dict: dict) -> None:
    """Fill rate stats from API values if present, otherwise derive from counting stats."""
    ab  = result.atBats
    h   = result.hits
    bb  = result.baseOnBalls
    hbp = result.hitByPitch
    sf  = result.sacFlies
    singles = max(h - result.doubles - result.triples - result.homeRuns, 0)
    tb = singles + 2*result.doubles + 3*result.triples + 4*result.homeRuns
    den_obp = ab + bb + hbp + sf

    def _pick(keys, num=None, den=None):
        for k in keys:
            v = stat_dict.get(k)
            if v not in (None, "", "---", ".---"):
                return fmt_avg(safe_float(v))
        if num is not None and den:
            return fmt_avg(num / den)
        return ".000"

    result.avg = _pick(["avg", "battingAverage", "batting_avg"],          h,        ab if ab else None)
    result.obp = _pick(["obp", "onBasePercentage", "on_base_pct"],        h+bb+hbp, den_obp if den_obp else None)
    result.slg = _pick(["slg", "sluggingPct", "slugging_pct"],            tb,       ab if ab else None)
    result.ops = _pick(["ops", "onBasePlusSlugging", "on_base_plus_slugging"])
    # If OPS wasn't in the API response, add OBP + SLG
    if result.ops == ".000" and result.obp not in ("N/A", ".000") and result.slg not in ("N/A", ".000"):
        try:
            o = safe_float("0" + result.obp if result.obp.startswith(".") else result.obp)
            s = safe_float("0" + result.slg if result.slg.startswith(".") else result.slg)
            result.ops = fmt_avg(o + s)
        except Exception:
            pass


def _fill_counting(result: "STCumulativeStats", s: dict) -> None:
    """Populate counting stats from a stat dict (works for both statsapi and bdfed shapes)."""
    result.games       = safe_int(s.get("gamesPlayed")   or s.get("games_played")  or s.get("g"))
    result.atBats      = safe_int(s.get("atBats")        or s.get("at_bats")       or s.get("ab"))
    result.hits        = safe_int(s.get("hits")          or s.get("h"))
    result.homeRuns    = safe_int(s.get("homeRuns")      or s.get("home_runs")     or s.get("hr"))
    result.rbi         = safe_int(s.get("rbi"))
    result.baseOnBalls = safe_int(s.get("baseOnBalls")   or s.get("walks")         or s.get("bb"))
    result.strikeOuts  = safe_int(s.get("strikeOuts")    or s.get("strike_outs")   or s.get("so") or s.get("k"))
    result.doubles     = safe_int(s.get("doubles")       or s.get("d"))
    result.triples     = safe_int(s.get("triples")       or s.get("t"))
    result.hitByPitch  = safe_int(s.get("hitByPitch")    or s.get("hbp"))
    result.sacFlies    = safe_int(s.get("sacFlies")      or s.get("sac_flies")     or s.get("sf"))


def _strategy_statsapi_hydrate(season: int) -> Optional["STCumulativeStats"]:
    """
    Strategy 1: Direct per-player hydrate call.
    URL shape confirmed via mlb_scraper source code.
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}"
        f"?hydrate=stats(group=hitting,type=season,season={season},gameType=S)"
    )
    log(f"ST strategy 1 (hydrate): {url}")
    data = fetch_json(url)
    people = data.get("people") or []
    if not people:
        return None
    stats_list = (people[0] or {}).get("stats") or []
    if not stats_list:
        return None
    splits = (stats_list[0] or {}).get("splits") or []
    if not splits:
        return None
    # Sum all splits (there may be one per team or one cumulative)
    # If only one split (cumulative), use it directly including its rate stats
    # If multiple splits (per-team), sum counting and re-derive rates
    if len(splits) == 1:
        s = splits[0].get("stat") or {}
        result = STCumulativeStats(found=True)
        _fill_counting(result, s)
        _derive_rates(result, s)
    else:
        result = STCumulativeStats(found=True)
        for sp in splits:
            s = sp.get("stat") or {}
            result.games       += safe_int(s.get("gamesPlayed") or s.get("g"))
            result.atBats      += safe_int(s.get("atBats")      or s.get("ab"))
            result.hits        += safe_int(s.get("hits")        or s.get("h"))
            result.homeRuns    += safe_int(s.get("homeRuns")    or s.get("hr"))
            result.rbi         += safe_int(s.get("rbi"))
            result.baseOnBalls += safe_int(s.get("baseOnBalls") or s.get("bb"))
            result.strikeOuts  += safe_int(s.get("strikeOuts")  or s.get("so"))
            result.doubles     += safe_int(s.get("doubles")     or s.get("d"))
            result.triples     += safe_int(s.get("triples")     or s.get("t"))
            result.hitByPitch  += safe_int(s.get("hitByPitch")  or s.get("hbp"))
            result.sacFlies    += safe_int(s.get("sacFlies")    or s.get("sf"))
        _derive_rates(result, {})
    log(f"  hydrate result: G={result.games} AB={result.atBats} H={result.hits} AVG={result.avg} OPS={result.ops}")
    return result if result.atBats > 0 else None


def _strategy_statsapi_people_stats(season: int) -> Optional["STCumulativeStats"]:
    """
    Strategy 2: /people/{id}/stats endpoint with gameType=S param.
    """
    url = (
        f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
        f"?stats=season&group=hitting&gameType=S&season={season}"
    )
    log(f"ST strategy 2 (/people/stats): {url}")
    data = fetch_json(url)
    stats_list = data.get("stats") or []
    if not stats_list:
        return None
    splits = (stats_list[0] or {}).get("splits") or []
    if not splits:
        return None
    result = STCumulativeStats(found=True)
    for sp in splits:
        s = sp.get("stat") or {}
        _fill_counting(result, s)
    _derive_rates(result, (splits[-1] or {}).get("stat") or {})
    log(f"  /people/stats result: G={result.games} AB={result.atBats} H={result.hits} AVG={result.avg}")
    return result if result.atBats > 0 else None


def _strategy_bdfed(season: int) -> Optional["STCumulativeStats"]:
    """
    Strategy 3: bdfed leaderboard scan.
    Field names confirmed from mlb_scraper open-source code:
      playerId, playerFullName, playerFirstName, playerLastName
    Counting stats use camelCase (atBats, homeRuns, etc.) per that source.
    """
    url = (
        f"https://bdfed.stitch.mlbinfra.com/bdfed/stats/player"
        f"?env=prod&season={season}&sportId=1&stats=season"
        f"&group=hitting&gameType=S&limit=2000&offset=0&sortStat=atBats&order=desc"
    )
    log(f"ST strategy 3 (bdfed): {url}")
    data = fetch_json(url)
    players = data.get("stats", [])
    log(f"  bdfed rows: {len(players)}")
    for p in players:
        pid = safe_int(p.get("playerId") or p.get("player_id") or 0)
        if pid != SWANSON_MLBAM_ID:
            continue
        result = STCumulativeStats(found=True)
        _fill_counting(result, p)
        _derive_rates(result, p)
        log(f"  bdfed result: G={result.games} AB={result.atBats} H={result.hits} AVG={result.avg} OPS={result.ops}")
        return result if result.atBats > 0 else None
    log(f"  Swanson not found in bdfed (id={SWANSON_MLBAM_ID})")
    return None


def fetch_st_cumulative_stats(season: int) -> STCumulativeStats:
    """Try all three strategies; return first success."""
    for strategy in (_strategy_statsapi_hydrate, _strategy_statsapi_people_stats, _strategy_bdfed):
        try:
            result = strategy(season)
            if result and result.found and result.atBats > 0:
                return result
        except Exception as e:
            log(f"ST strategy {strategy.__name__} error: {e}")
    log("All ST stat strategies exhausted or returned 0 AB.")
    return STCumulativeStats()  # empty — renders as "no PA yet"

def render_st_stats_text(st: STCumulativeStats) -> str:
    if not st.found or st.atBats == 0:
        return "Spring Training Offense (season-to-date): No plate appearances yet.\n"
    lines = [
        "Spring Training Offense (season-to-date)", "",
        f"{'G':<5} {'AB':>4} {'H':>4} {'HR':>4} {'RBI':>5} {'AVG':>6} {'OBP':>6} {'SLG':>6} {'OPS':>6}",
        "-" * 55,
        f"{st.games:<5} {st.atBats:>4} {st.hits:>4} {st.homeRuns:>4} {st.rbi:>5} "
        f"{st.avg:>6} {st.obp:>6} {st.slg:>6} {st.ops:>6}", "",
    ]
    return "\n".join(lines)

def render_st_stats_html(st: STCumulativeStats) -> str:
    if not st.found or st.atBats == 0:
        return "<p style='color:#888; font-style:italic;'>Spring Training stats: No plate appearances recorded yet.</p>"
    return (
        "<h3 style='margin:10px 0 6px 0;'>Spring Training Offense (season-to-date)</h3>"
        "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse; border-color:#ddd; width:100%; max-width:780px;'>"
        "<tr><th>G</th><th>AB</th><th>H</th><th>HR</th><th>RBI</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th></tr>"
        f"<tr><td align='right'>{st.games}</td><td align='right'>{st.atBats}</td>"
        f"<td align='right'>{st.hits}</td><td align='right'>{st.homeRuns}</td>"
        f"<td align='right'>{st.rbi}</td><td align='right'>{st.avg}</td>"
        f"<td align='right'>{st.obp}</td><td align='right'>{st.slg}</td>"
        f"<td align='right'>{st.ops}</td></tr>"
        "</table>"
    )

# -------------------------
# Offense rollups (regular season only)
# -------------------------
def sum_batting(rows: List[GameRow]) -> dict:
    t = {k: 0 for k in ("atBats","hits","homeRuns","rbi","baseOnBalls","strikeOuts","doubles","triples","hitByPitch","sacFlies")}
    for r in rows:
        for k in t:
            t[k] += safe_int((r.batting or {}).get(k))
    return t

def rate_stats(t: dict) -> dict:
    ab=safe_int(t.get("atBats")); h=safe_int(t.get("hits")); bb=safe_int(t.get("baseOnBalls"))
    hbp=safe_int(t.get("hitByPitch")); sf=safe_int(t.get("sacFlies")); d=safe_int(t.get("doubles"))
    tri=safe_int(t.get("triples")); hr=safe_int(t.get("homeRuns"))
    tb = max(h-d-tri-hr,0) + 2*d + 3*tri + 4*hr
    den = ab+bb+hbp+sf
    return {
        "AVG": h/ab if ab else 0.0,
        "OBP": (h+bb+hbp)/den if den else 0.0,
        "SLG": tb/ab if ab else 0.0,
        "OPS": (h+bb+hbp)/den + tb/ab if (den and ab) else 0.0,
    }

def build_roll_rows(rows: List[GameRow]) -> List[Tuple[str, dict, dict]]:
    return [(lbl, sum_batting(s), rate_stats(sum_batting(s)))
            for lbl, s in (("Last Game", rows[:1]), ("Last 10", rows[:10]), ("Last 30", rows[:30]))]

def render_table_text(rows: List[Tuple[str, dict, dict]]) -> str:
    lines = ["Offense (Rolling)","",
             f"{'Split':<10} {'AB':>4} {'H':>4} {'HR':>4} {'RBI':>5} {'AVG':>6} {'OBP':>6} {'SLG':>6} {'OPS':>6}",
             "-"*65]
    for lbl,t,r in rows:
        lines.append(f"{lbl:<10} {t['atBats']:>4} {t['hits']:>4} {t['homeRuns']:>4} {t['rbi']:>5} "
                     f"{fmt_avg(r['AVG']):>6} {fmt_avg(r['OBP']):>6} {fmt_avg(r['SLG']):>6} {fmt_avg(r['OPS']):>6}")
    lines.append("")
    return "\n".join(lines)

def render_table_html(rows: List[Tuple[str, dict, dict]]) -> str:
    tr = ["<tr><th align='left'>Split</th><th>AB</th><th>H</th><th>HR</th><th>RBI</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th></tr>"]
    for lbl,t,r in rows:
        tr.append(f"<tr><td>{escape_html(lbl)}</td><td align='right'>{t['atBats']}</td>"
                  f"<td align='right'>{t['hits']}</td><td align='right'>{t['homeRuns']}</td>"
                  f"<td align='right'>{t['rbi']}</td><td align='right'>{fmt_avg(r['AVG'])}</td>"
                  f"<td align='right'>{fmt_avg(r['OBP'])}</td><td align='right'>{fmt_avg(r['SLG'])}</td>"
                  f"<td align='right'>{fmt_avg(r['OPS'])}</td></tr>")
    return ("<h3 style='margin:10px 0 6px 0;'>Offense (Rolling)</h3>"
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse; border-color:#ddd; width:100%; max-width:780px;'>"
            + "".join(tr) + "</table>")

# -------------------------
# RISP
# -------------------------
def get_risp_avg(stat_type: str) -> str:
    try:
        url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
               f"?stats={stat_type}&group=hitting&sitCodes=risp")
        data = fetch_json(url)
        splits = ((data.get("stats") or [{}])[0] or {}).get("splits") or []
        avg = (splits[0] or {}).get("stat", {}).get("avg") if splits else None
        return fmt_avg(safe_float(avg)) if avg else "N/A"
    except Exception:
        return "N/A"

# -------------------------
# SS OPS leaders
# -------------------------
def get_ss_ops_leaders_by_league(limit: int = 5) -> Tuple[str, str]:
    today = date.today()
    if is_spring_training(today):
        opens = REGULAR_SEASON_START.strftime("%B %-d")
        return (f"NL SS OPS: Regular season opens {opens}", f"AL SS OPS: Regular season opens {opens}")
    try:
        yr = today.year
        url = (f"https://statsapi.mlb.com/api/v1/stats/leaders"
               f"?leaderCategories=onBasePlusSlugging&statGroup=hitting&season={yr}&sportId=1&limit=200")
        entries = (((fetch_json(url).get("leagueLeaders") or [{}])[0] or {}).get("leaders") or [])[:80]

        def pos(pid): 
            try: return (((fetch_json(f"https://statsapi.mlb.com/api/v1/people/{pid}?hydrate=currentTeam").get("people") or [{}])[0] or {}).get("primaryPosition") or {}).get("abbreviation","")
            except: return ""

        def league(pid):
            try:
                ppl = ((fetch_json(f"https://statsapi.mlb.com/api/v1/people/{pid}?hydrate=currentTeam").get("people") or [{}])[0] or {})
                tid = (ppl.get("currentTeam") or {}).get("id")
                if not tid: return ""
                return (((fetch_json(f"https://statsapi.mlb.com/api/v1/teams/{tid}").get("teams") or [{}])[0] or {}).get("league") or {}).get("name","")
            except: return ""

        nl, al = [], []
        for e in entries:
            pid=safe_int((e.get("person") or {}).get("id")); name=(e.get("person") or {}).get("fullName",""); val=e.get("value","")
            if not (pid and name and val) or pos(pid)!="SS": continue
            lg=league(pid); item=f"{name} {val}"
            if "National" in lg: nl.append(item)
            elif "American" in lg: al.append(item)
            if len(nl)>=limit and len(al)>=limit: break
        return ("NL SS OPS: "+(",".join(nl[:limit]) if nl else "N/A"), "AL SS OPS: "+(",".join(al[:limit]) if al else "N/A"))
    except Exception as e:
        log(f"ss_leaders error: {e}")
        return ("NL SS OPS: N/A","AL SS OPS: N/A")

# -------------------------
# Advanced defense
# -------------------------
def load_csv_rows(src: str) -> List[Dict[str, str]]:
    src=(src or "").strip()
    if not src: return []
    text = requests.get(src, timeout=HTTP_TIMEOUT).text if src.startswith("http") else Path(src).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))

def find_swanson_row(rows):
    keys=("player_name","Name","name","player","Player","playerName")
    for row in rows:
        for k in keys:
            v=row.get(k,"")
            if "Swanson" in v and "Dansby" in v: return row
    for row in rows:
        for k in keys:
            if "Swanson" in row.get(k,""): return row
    return None

def get_advanced_defense() -> Dict[str, str]:
    out={}
    for url_var, key_list, label in [
        (SAVANT_OAA_CSV_URL, ("oaa","OAA","outs_above_average","OAA_total"), "OAA"),
        (SAVANT_FRV_CSV_URL, ("frv","FRV","fielding_run_value","Fielding Run Value"), "Fielding Run Value"),
    ]:
        if url_var:
            try:
                row=find_swanson_row(load_csv_rows(url_var))
                if row:
                    for k in key_list:
                        if k in row and row[k]!="":
                            out[label]=row[k]; break
            except Exception as e:
                out[label]=f"(error: {e})"
    return out

# -------------------------
# Daily Insight (regular season only)
# -------------------------
def build_daily_insight(roll_rows) -> List[str]:
    by={lbl.lower():(t,r) for lbl,t,r in roll_rows}
    _,r10=by.get("last 10",({},{})); _,r30=by.get("last 30",({},{}))
    ops10=safe_float(r10.get("OPS")); ops30=safe_float(r30.get("OPS")); d=ops10-ops30
    if abs(d)>=0.050:
        return [f"OPS trend: Last 10 ({fmt_avg(ops10)}) vs Last 30 ({fmt_avg(ops30)}) — {'+'if d>=0 else ''}{d:.3f}"]
    return []

# -------------------------
# Email build
# -------------------------
def build_email(game: GameRow, recent: List[GameRow]) -> Tuple[str, str, str]:
    today = date.today()
    in_st = is_spring_training(today)

    picks = random.sample(DANSBY_ACCOLADES, k=min(5, len(DANSBY_ACCOLADES)))
    accolades_html = (
        "<div style='padding:10px 12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;margin-bottom:10px;'>"
        "<div style='font-weight:bold;margin-bottom:6px;'>🌟 Dansby Swanson Accolades of the Day 🌟</div>"
        "<ul style='margin:0 0 0 18px;padding:0;'>"
        + "".join(f"<li>{escape_html(p)}</li>" for p in picks) + "</ul></div>"
    )
    accolades_text = "🌟 Dansby Swanson Accolades of the Day 🌟\n\n" + "\n".join(f"- {p}" for p in picks) + "\n\n"

    if in_st:
        st = fetch_st_cumulative_stats(today.year)
        offense_text = render_st_stats_text(st)
        offense_html = render_st_stats_html(st)
        insight: List[str] = []
    else:
        roll_rows = build_roll_rows(recent)
        offense_text = render_table_text(roll_rows)
        offense_html = render_table_html(roll_rows)
        insight = build_daily_insight(roll_rows)

    risp_season = get_risp_avg("season")
    risp_career  = get_risp_avg("career")
    nl_line, al_line = get_ss_ops_leaders_by_league()
    f = game.fielding or {}
    fielding_line = f"PO {safe_int(f.get('putOuts'))}, A {safe_int(f.get('assists'))}, E {safe_int(f.get('errors'))}"
    adv = get_advanced_defense()

    subject = f"Dansby Swanson Digest — {game.game_date} vs {game.opponent}"

    # TEXT
    text = [accolades_text.rstrip(), ""]
    if insight:
        text += ["Daily Insight:"] + [f"- {b}" for b in insight] + [""]
    text += [f"Dansby Swanson — {game.game_date} vs {game.opponent}", "",
             "Last game defense (traditional):", f"- {fielding_line}", "",
             offense_text.rstrip(), "",
             "Runners in Scoring Position (AVG):",
             f"- Dansby Swanson (season): {risp_season}",
             f"- Dansby Swanson (career): {risp_career}",
             f"- Shawon Dunston (career): {DUNSTON_CAREER_RISP_AVG}", "",
             "Shortstop comparison (regular season, by OPS):", nl_line, al_line, ""]
    if adv:
        text += ["Advanced defense (season-to-date):"] + [f"- {k}: {v}" for k,v in adv.items()] + [""]
    text_body = "\n".join(text)

    # HTML helpers
    insight_html = (
        "<h3 style='margin:10px 0 6px 0;'>Daily Insight</h3><ul style='margin:0 0 10px 18px;padding:0;'>"
        + "".join(f"<li>{escape_html(b)}</li>" for b in insight) + "</ul>"
    ) if insight else ""

    adv_html = (
        "<h3 style='margin:10px 0 6px 0;'>Advanced defense (season-to-date)</h3>"
        "<ul style='margin:0 0 10px 18px;padding:0;'>"
        + "".join(f"<li><b>{escape_html(k)}:</b> {escape_html(v)}</li>" for k,v in adv.items()) + "</ul>"
    ) if adv else ""

    html_body = f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.4;">
      {accolades_html}
      {insight_html}
      <h2 style="margin:0 0 8px 0;">Dansby Swanson — {escape_html(game.game_date)} vs {escape_html(game.opponent)}</h2>
      <h3 style="margin:10px 0 6px 0;">Last game defense (traditional)</h3>
      <div style="margin:0 0 10px 0;">{escape_html(fielding_line)}</div>
      {offense_html}
      <h3 style="margin:10px 0 6px 0;">Runners in Scoring Position (AVG)</h3>
      <ul style="margin:0 0 10px 18px;padding:0;">
        <li><strong>Dansby Swanson (season):</strong> {escape_html(risp_season)}</li>
        <li><strong>Dansby Swanson (career):</strong> {escape_html(risp_career)}</li>
        <li><strong>Shawon Dunston (career):</strong> {DUNSTON_CAREER_RISP_AVG}</li>
      </ul>
      <h3 style="margin:10px 0 6px 0;">Shortstop comparison (regular season, by OPS)</h3>
      <ul style="margin:0 0 10px 18px;padding:0;">
        <li>{escape_html(nl_line)}</li><li>{escape_html(al_line)}</li>
      </ul>
      {adv_html}
      <div style="color:#666;font-size:12px;margin-top:12px;">GamePk: {game.gamePk}</div>
    </div>"""
    return subject, text_body, html_body

# -------------------------
# Gmail OAuth
# -------------------------
def get_gmail_service():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    token_path = Path("token.json")
    if not token_path.exists():
        raise FileNotFoundError("token.json not found")
    creds = Credentials.from_authorized_user_file(str(token_path), ["https://www.googleapis.com/auth/gmail.send"])
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)

def send_gmail(sender, recipients, subject, text_body, html_body):
    if not sender:
        raise ValueError("SENDER_EMAIL is empty.")
    msg = MIMEMultipart("alternative")
    msg["To"] = ", ".join(recipients); msg["From"] = sender; msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain")); msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    get_gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()

# -------------------------
# Entrypoints
# -------------------------
def send_test_email_now() -> None:
    init_db()
    today = date.today()
    recent = load_recent_games_with_swanson(today, ROLLING_LOOKBACK_DAYS)
    anchor = next((r for r in recent
                   if (lambda d: d < today)(date.fromisoformat((r.game_date or "1900-01-01")[:10]))), None)

    if not anchor:
        if not FORCE_TEST_EMAIL:
            print("No final Cubs game found before today. Check dansbytracker.log.")
            return
        print("FORCE_TEST_EMAIL — sending mock email with real ST stats pulled live.")
        anchor = GameRow(gamePk=999999999, game_date=today.isoformat(), opponent="TEST OPPONENT", batting={}, fielding={})
        recent = []

    subject, text_body, html_body = build_email(anchor, recent)
    subject = "[TEST EMAIL] " + subject
    to_list = TEST_TO_EMAILS or ["robertjsherman1@gmail.com"]
    send_gmail(SENDER_EMAIL, to_list, subject, text_body, html_body)
    print(f"Test email sent to: {', '.join(to_list)}")

def main() -> None:
    init_db()
    today = date.today()
    if today < EARLIEST_SEND_DATE and not TEST_MODE:
        print(f"Not yet. Starts {EARLIEST_SEND_DATE}. Today={today}")
        return
    if TEST_MODE:
        send_test_email_now()
        return
    anchor = pick_unsent_anchor_game(today, SEND_LOOKBACK_DAYS)
    if not anchor:
        print(f"No new Cubs game with Swanson in last {SEND_LOOKBACK_DAYS} days. Check dansbytracker.log.")
        return
    recent = load_recent_games_with_swanson(today, ROLLING_LOOKBACK_DAYS)
    subject, text_body, html_body = build_email(anchor, recent)
    send_gmail(SENDER_EMAIL, RECIPIENTS, subject, text_body, html_body)
    mark_sent(anchor.gamePk)
    print(f"Sent digest for gamePk={anchor.gamePk} to {len(RECIPIENTS)} recipients.")

if __name__ == "__main__":
    main()

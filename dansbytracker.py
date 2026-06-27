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

import io as _io
import base64 as _base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
    "Dansby Swanson is currently batting his weight. Unfortunately his weight is .187.",
    "He saw 4 pitches today. Swung at 3. Made contact with 0. Progress.",
    "At this point the Cubs are paying $177 million for a very expensive glove.",
    "Dansby's bat has been so cold it has its own weather advisory.",
    "He stepped up to the plate today with all the urgency of a man who knows he's going to strike out.",
    "Fun fact: Dansby's OPS is lower than the temperature at a Cubs night game in April.",
    "The pitcher saw Dansby coming and visibly relaxed.",
    "Somewhere a AAA shortstop is watching this and feeling very confident.",
    "Dansby Swanson: proof that a Gold Glove cannot hit a curveball.",
    "His xBA says .232. His actual BA says .187. Even the math is embarrassed for him.",
    "He went 0-for-4 today and somehow looked surprised each time.",
    "The only thing Dansby is hitting consistently is rock bottom.",
    "Cubs fans paid to watch baseball. Dansby is out there playing a different sport.",
    "He fouled one off today. The crowd went wild. That's where we are.",
    "Dansby's bat speed is fine. It's the bat accuracy that's the issue.",
    "At this rate he'll finish the season with a batting average you'd be embarrassed to leave as a tip.",
    "The opposing pitcher's ERA went down just by seeing Dansby's name in the lineup.",
    "He's not in a slump. A slump implies there was something to fall from.",
    "Dansby Swanson is single-handedly keeping the strikeout statistic alive and well.",
    "If his bat were a restaurant it would have a health code violation.",
    "He took a called third strike today. The ball was in the zone. Dansby was not.",
    "His BABIP is .188. The universe is not conspiring against him. He is just not hitting the ball.",
    "Every time Dansby steps to the plate, somewhere a pitcher's confidence fully restores.",
    "He grounded into a double play today. It was the most contact he's made all week.",
    "The good news: Dansby is still elite defensively. The bad news: you still need to bat.",
    "His launch angle today was perfect — perfectly into the catcher's mitt.",
    "Cubs fans have started bringing books to read during his at-bats.",
    "Dansby looks at strike three the way most people look at an old friend.",
    "He had a full count today and the crowd held its breath. They were right to be nervous.",
    "At this point his batting average has more in common with a golf score.",
    "The pitcher threw him a fastball right down the middle. Dansby took it personally and let it go.",
    "His RBI total is so low it's starting to feel intentional.",
    "Dansby Swanson: making $23 million a year to remind us all that defense doesn't win championships alone.",
    "He went 1-for-4 today. The Cubs front office wept with relief.",
    "His batting average is so low that his expected batting average feels like trash talk.",
    "Dansby walked today. The crowd gave him a standing ovation. He looked confused.",
    "He watched strike three go by with the calm of a man at peace with his decisions.",
    "The Cubs signed him to a seven-year deal. They are now in year three of learning what that means.",
    "His barrel rate is fine. His barrel-to-hit conversion rate is a different story.",
    "Dansby's approach at the plate: take, take, swing weakly, jog back to the dugout.",
    "He made contact today. It went directly to the second baseman, who had time to wave at the crowd first.",
    "Every pitcher in the NL Central has Dansby circled on the lineup card. Not as a threat — as a rest stop.",
    "He struck out looking in a key spot today. On the bright side, he really committed to the bit.",
    "The Cubs' offensive struggles this week can be summarized in one name. You already know the name.",
    "Somewhere a sabermetrician is staring at Dansby's spray chart and quietly weeping.",
    "He went 0-for-3 with a walk. The walk was not his idea.",
    "Dansby Swanson has elite exit velocity on his groundouts. They just never seem to find a gap.",
    "His hard-hit rate is actually solid. His hard-hit-in-a-useful-direction rate is less so.",
    "The pitcher threw him four straight sliders in the dirt. Dansby considered all of them carefully before striking out on one.",
    "He's been in the lineup every day. His bat has taken a few more days off.",
    "Dansby swung at a pitch six inches off the plate today. In his defense, it was the closest one to the zone all game.",
    "At this point opposing closers are actively requesting to face him in save situations.",
    "He fouled a ball straight back today, which means he was only slightly late on a pitch he should have crushed.",
    "The Cubs have a $177 million shortstop with a .730 OPS. The good news is the glove work is immaculate. The bad news is everything else.",
    "He popped up to end the inning with two on and two out. Somewhere, a pitcher pumped his fist so hard he pulled a muscle.",
    "Dansby's stat line reads like a ransom note written by someone who gave up halfway through.",
    "He laced a single to left today. The Cubs posted a highlight. Expectations have been recalibrated.",
    "His launch angle is below average, his exit velocity is average, and his batting average is below the Mendoza Line. One of these things is doing a lot of work.",
    "The umpire called strike three. Dansby looked at the umpire. The umpire looked back. Both knew.",
    "He's fourth in Cubs history in career Gold Gloves and somewhere around 400th in career useful plate appearances this season.",
    "A pitcher threw him a cookie and Dansby let it pass, apparently saving it for later.",
    "His OPS+ is aggressively in the double digits. Aggressively.",
    "Dansby Swanson: bringing the same energy to every at-bat regardless of the score, the inning, or the laws of baseball.",
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
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS sent_games (gamePk INTEGER PRIMARY KEY, sent_at TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS used_accolades (accolade TEXT PRIMARY KEY, used_at TEXT)")
        cur.execute("""CREATE TABLE IF NOT EXISTS game_grades (
            gamePk INTEGER PRIMARY KEY,
            game_date TEXT,
            grade TEXT,
            sent_at TEXT
        )""")
        conn.commit()
    finally:
        conn.close()

def save_game_grade(game_pk: int, game_date: str, grade: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.cursor().execute(
            "INSERT OR REPLACE INTO game_grades (gamePk, game_date, grade, sent_at) VALUES (?,?,?,?)",
            (game_pk, game_date, grade, datetime.utcnow().isoformat() + "Z"),
        )
        conn.commit()
    finally:
        conn.close()

def get_grade_tally() -> dict:
    """Returns count of each grade issued so far this season."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.cursor().execute(
            "SELECT grade, COUNT(*) FROM game_grades GROUP BY grade ORDER BY grade"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()

def get_monthly_grade_summary() -> List[dict]:
    """
    Returns a list of months with their grade distribution and average grade score.
    Each entry: {month: "April 2026", tally: {"A+": 2, "B": 3, ...}, avg_score: 68.2, avg_grade: "B"}
    """
    GRADE_SCORES = {"A+": 95, "A": 85, "B+": 75, "B": 65, "C+": 55, "C": 45, "D": 35, "F": 15}

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.cursor().execute(
            "SELECT game_date, grade FROM game_grades ORDER BY game_date"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Group by month
    from collections import defaultdict
    monthly: dict = defaultdict(list)
    for game_date, grade in rows:
        try:
            d = date.fromisoformat(game_date[:10])
            key = d.strftime("%B %Y")
            monthly[key].append(grade)
        except Exception:
            continue

    result = []
    for month_label, grades in monthly.items():
        tally = {}
        for g in grades:
            tally[g] = tally.get(g, 0) + 1
        scores = [GRADE_SCORES.get(g, 50) for g in grades]
        avg_score = sum(scores) / len(scores) if scores else 0
        # Convert avg score back to a grade
        if avg_score >= 90:   avg_grade = "A+"
        elif avg_score >= 80: avg_grade = "A"
        elif avg_score >= 70: avg_grade = "B+"
        elif avg_score >= 60: avg_grade = "B"
        elif avg_score >= 50: avg_grade = "C+"
        elif avg_score >= 40: avg_grade = "C"
        elif avg_score >= 30: avg_grade = "D"
        else:                 avg_grade = "F"
        result.append({
            "month": month_label,
            "tally": tally,
            "avg_score": round(avg_score, 1),
            "avg_grade": avg_grade,
            "games": len(grades),
        })
    return result

def pick_accolades(n: int = 5) -> List[str]:
    """
    Pick n accolades, avoiding recently used ones.
    Tracks usage in DB and resets once all have been used.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS used_accolades (accolade TEXT PRIMARY KEY, used_at TEXT)")
        # Get recently used
        used = {r[0] for r in cur.execute("SELECT accolade FROM used_accolades").fetchall()}
        # Get available (not recently used)
        available = [a for a in DANSBY_ACCOLADES if a not in used]
        # If we've used most of them, reset and start fresh
        if len(available) < n:
            cur.execute("DELETE FROM used_accolades")
            conn.commit()
            available = list(DANSBY_ACCOLADES)
        # Pick n random from available
        picks = random.sample(available, k=min(n, len(available)))
        # Mark as used
        now = datetime.utcnow().isoformat() + "Z"
        for p in picks:
            cur.execute("INSERT OR REPLACE INTO used_accolades (accolade, used_at) VALUES (?,?)", (p, now))
        conn.commit()
        return picks
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
    # During regular season, never look back before Opening Day to keep ST games out
    if not is_spring_training(today):
        start = max(today - timedelta(days=lookback_days), REGULAR_SEASON_START)
    else:
        start = today - timedelta(days=lookback_days)
    games = fetch_team_schedule_with_fallbacks(TEAM_ID_CUBS, start, today)
    rows: List[GameRow] = []
    for g in games:
        if not game_is_final(g):
            continue
        game_pk = g.get("gamePk")
        if not game_pk:
            continue
        game_date_str = (g.get("officialDate") or (g.get("gameDate") or "")[:10] or "")
        # Hard filter: skip future-dated and pre-Opening Day games
        try:
            game_date_obj = date.fromisoformat(game_date_str)
            if game_date_obj > today:
                log(f"Skipping future-dated game {game_pk} ({game_date_str})")
                continue
            if not is_spring_training(today) and game_date_obj < REGULAR_SEASON_START:
                log(f"Skipping pre-RS game {game_pk} ({game_date_str})")
                continue
        except Exception:
            pass
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
            game_date=game_date_str,
            opponent=opponent_for_team(g),
            batting=batting,
            fielding=fielding,
        ))
    # Deduplicate by gamePk — fallback schedule queries can return the same game twice
    seen = set()
    deduped = []
    for r in rows:
        if r.gamePk not in seen:
            seen.add(r.gamePk)
            deduped.append(r)
    log(f"load_recent_games: {len(deduped)} game(s) with Swanson (deduped from {len(rows)}).")
    return deduped

def pick_unsent_anchor_group(today: date, lookback_days: int) -> List[GameRow]:
    """Return all unsent games for the most recent unsent date (handles doubleheaders)."""
    all_games = load_recent_games_with_swanson(today, lookback_days)
    unsent: List[Tuple[date, GameRow]] = []
    for r in all_games:
        try:
            gd = date.fromisoformat((r.game_date or "")[:10])
        except Exception:
            continue
        if gd < today and not was_sent(r.gamePk):
            unsent.append((gd, r))
    if not unsent:
        return []
    target_date = max(gd for gd, _ in unsent)
    return [r for gd, r in unsent if gd == target_date]

def merge_game_rows(games: List[GameRow]) -> GameRow:
    """Merge multiple games (doubleheader) into one GameRow with summed stats."""
    if len(games) == 1:
        return games[0]
    batting_keys = ("atBats","hits","homeRuns","rbi","baseOnBalls","strikeOuts",
                    "doubles","triples","hitByPitch","sacFlies","sacBunts")
    fielding_keys = ("putOuts","assists","errors","doublePlays")
    merged_batting = {k: sum(safe_int((g.batting or {}).get(k)) for g in games) for k in batting_keys}
    merged_fielding = {k: sum(safe_int((g.fielding or {}).get(k)) for g in games) for k in fielding_keys}
    return GameRow(
        gamePk=games[0].gamePk,
        game_date=games[0].game_date,
        opponent=games[0].opponent,
        batting=merged_batting,
        fielding=merged_fielding,
    )

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
    out = [(lbl, sum_batting(s), rate_stats(sum_batting(s)))
           for lbl, s in (("Last Game", rows[:1]), ("Last 10", rows[:10]), ("Last 30", rows[:30]))]
    # Season row: always use the MLB Stats API directly — most accurate source
    season = fetch_season_totals()
    if season:
        out.append(("Season", season[0], season[1]))
    return out

def render_table_text(rows: List[Tuple[str, dict, dict]]) -> str:
    lines = ["Offense (Rolling)","",
             f"{'Split':<10} {'AB':>4} {'H':>4} {'HR':>4} {'RBI':>5} {'AVG':>6} {'OBP':>6} {'SLG':>6} {'OPS':>6}",
             "-"*65]
    for lbl,t,r in rows:
        lines.append(f"{lbl:<10} {t['atBats']:>4} {t['hits']:>4} {t['homeRuns']:>4} {t['rbi']:>5} "
                     f"{fmt_avg(r['AVG']):>6} {fmt_avg(r['OBP']):>6} {fmt_avg(r['SLG']):>6} {fmt_avg(r['OPS']):>6}")
    lines.append("")
    return "\n".join(lines)

def render_table_html(rows: List[Tuple[str, dict, dict]], qoc: Optional[dict] = None, avgs: Optional[dict] = None) -> str:
    tr = ["<tr><th align='left'>Split</th><th>AB</th><th>H</th><th>HR</th><th>RBI</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th></tr>"]
    for lbl,t,r in rows:
        tr.append(f"<tr><td>{escape_html(lbl)}</td><td align='right'>{t['atBats']}</td>"
                  f"<td align='right'>{t['hits']}</td><td align='right'>{t['homeRuns']}</td>"
                  f"<td align='right'>{t['rbi']}</td><td align='right'>{fmt_avg(r['AVG'])}</td>"
                  f"<td align='right'>{fmt_avg(r['OBP'])}</td><td align='right'>{fmt_avg(r['SLG'])}</td>"
                  f"<td align='right'>{fmt_avg(r['OPS'])}</td></tr>")
    xstats_html = ""
    if qoc and any(qoc.get(k) not in (None, "N/A", "") for k in ("xba","xobp","xslg","xwoba")):
        xstats_html = (
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;margin-top:4px;'>"
            "<tr style='background:#f0f0f0;'>"
            "<th align='left' colspan='2'>Expected Stats</th>"
            "<th align='center'>xBA</th><th align='center'>xOBP</th>"
            "<th align='center'>xSLG</th><th align='center'>xwOBA</th>"
            "</tr>"
            "<tr style='background:#f5f5f5;'>"
            "<td colspan='2'><b>Dansby</b></td>"
            f"<td align='center'><b>{qoc.get('xba','N/A')}</b></td>"
            f"<td align='center'><b>{qoc.get('xobp','N/A')}</b></td>"
            f"<td align='center'><b>{qoc.get('xslg','N/A')}</b></td>"
            f"<td align='center'><b>{qoc.get('xwoba','N/A')}</b></td>"
            "</tr>"
            "</table>"
        )
    table = ("<h3 style='margin:10px 0 6px 0;'>Offense (Rolling)</h3>"
             "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse; border-color:#ddd; width:100%; max-width:780px;'>"
             + "".join(tr) + "</table>" + xstats_html)
    if qoc:
        table += (
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;margin-top:4px;'>"
            "<tr style='background:#f0f0f0;'><th align='left' colspan='2'></th>"
            "<th align='center'>Barrel%</th><th align='center'>Hard Hit%</th>"
            "<th align='center'>Exit Velo</th><th align='center'>Launch Angle</th></tr>"
            "<tr style='background:#f5f5f5;'>"
            "<td colspan='2'><b>Dansby</b></td>"
            f"<td align='center'><b>{qoc['barrel_pct']}%</b></td>"
            f"<td align='center'><b>{qoc['hard_hit']}%</b></td>"
            f"<td align='center'><b>{qoc['exit_velo']} mph</b></td>"
            f"<td align='center'><b>{qoc['launch_ang']}°</b></td>"
            "</tr>"
        )
        if avgs:
            table += (
                "<tr style='background:#fafafa;color:#555;font-style:italic;'>"
                "<td colspan='2'>SS Avg</td>"
                f"<td align='center'>{avgs.get('barrel_pct','')}%</td>"
                f"<td align='center'>{avgs.get('hard_hit','')}%</td>"
                f"<td align='center'>{avgs.get('exit_velo','')} mph</td>"
                f"<td align='center'>{avgs.get('launch_ang','')}°</td>"
                "</tr></table>"
            )
    return table

# -------------------------
# RISP
# -------------------------
def get_risp_avg(stat_type: str) -> str:
    """
    Fetch AVG with runners in scoring position (2nd and/or 3rd base).
    Uses statSplits + sitCodes=risp for the correct RISP subset.
    stat_type: "season" uses current year; "career" aggregates all years.
    """
    try:
        yr = date.today().year
        if stat_type == "season":
            url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
                   f"?stats=statSplits&group=hitting&sitCodes=risp&season={yr}&sportId=1")
        else:
            # Career: use statSplits across all seasons
            url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
                   f"?stats=careerStatSplits&group=hitting&sitCodes=risp&sportId=1")
        data = fetch_json(url)
        splits = ((data.get("stats") or [{}])[0] or {}).get("splits") or []
        avg = (splits[0] or {}).get("stat", {}).get("avg") if splits else None
        return avg if avg else "N/A"
    except Exception:
        return "N/A"

# -------------------------
# Season cumulative stats
# -------------------------
def fetch_season_totals() -> Optional[Tuple[dict, dict]]:
    """Fetch Swanson's full season cumulative batting stats."""
    try:
        yr = date.today().year
        url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
               f"?stats=season&group=hitting&season={yr}&sportId=1")
        data = fetch_json(url)
        splits = ((data.get("stats") or [{}])[0] or {}).get("splits") or []
        if not splits:
            return None
        s = splits[0].get("stat") or {}
        totals = {
            "atBats":      safe_int(s.get("atBats")),
            "hits":        safe_int(s.get("hits")),
            "homeRuns":    safe_int(s.get("homeRuns")),
            "rbi":         safe_int(s.get("rbi")),
            "baseOnBalls": safe_int(s.get("baseOnBalls")),
            "strikeOuts":  safe_int(s.get("strikeOuts")),
            "doubles":     safe_int(s.get("doubles")),
            "triples":     safe_int(s.get("triples")),
            "hitByPitch":  safe_int(s.get("hitByPitch")),
            "sacFlies":    safe_int(s.get("sacFlies")),
        }
        rates = {
            "AVG": safe_float(s.get("avg")),
            "OBP": safe_float(s.get("obp")),
            "SLG": safe_float(s.get("slg")),
            "OPS": safe_float(s.get("ops")),
        }
        return totals, rates
    except Exception as e:
        log(f"fetch_season_totals error: {e}")
        return None

# -------------------------
# Season fielding stats
# -------------------------
def fetch_fielding_stats() -> Optional[dict]:
    """Fetch Swanson's season fielding stats."""
    try:
        yr = date.today().year
        url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
               f"?stats=season&group=fielding&season={yr}&sportId=1")
        data = fetch_json(url)
        splits = ((data.get("stats") or [{}])[0] or {}).get("splits") or []
        if not splits:
            return None
        return splits[0].get("stat") or {}
    except Exception as e:
        log(f"fetch_fielding_stats error: {e}")
        return None

# -------------------------
# SS OPS full list (all qualified starters, Dansby highlighted)
# -------------------------
SS_MIN_AB = 80  # minimum AB to qualify as a starter

def get_ss_ops_ranked() -> List[dict]:
    """
    Returns all qualified SS (minimum AB threshold) sorted by OPS desc.
    Each entry: {name, ops, ab, pid, is_dansby}
    """
    today = date.today()
    if is_spring_training(today):
        return []
    try:
        yr = today.year
        url = (f"https://statsapi.mlb.com/api/v1/stats"
               f"?stats=season&group=hitting&season={yr}&sportId=1"
               f"&position=SS&limit=100&offset=0&sortStat=onBasePlusSlugging&order=desc")
        data = fetch_json(url)
        splits = (data.get("stats") or [{}])[0].get("splits") or []
        result = []
        for s in splits:
            pid  = safe_int((s.get("player") or {}).get("id"))
            name = (s.get("player") or {}).get("fullName","")
            stat = s.get("stat") or {}
            ab   = safe_int(stat.get("atBats"))
            ops  = stat.get("ops","")
            if not pid or not name or not ops or ab < SS_MIN_AB:
                continue
            result.append({
                "name": name,
                "ops":  ops,
                "ab":   ab,
                "pid":  pid,
                "is_dansby": pid == SWANSON_MLBAM_ID,
            })
        return result
    except Exception as e:
        log(f"get_ss_ops_ranked error: {e}")
        return []

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
# High leverage & late/close splits
# -------------------------
def get_situation_stats() -> dict:
    """Fetch high leverage and late & close hitting splits for the season."""
    result = {}
    yr = date.today().year
    for label, sitcode in (("high_leverage", "h"), ("late_close", "lc")):
        try:
            url = (f"https://statsapi.mlb.com/api/v1/people/{SWANSON_MLBAM_ID}/stats"
                   f"?stats=statSplits&group=hitting&sitCodes={sitcode}&season={yr}&sportId=1")
            data = fetch_json(url)
            splits = ((data.get("stats") or [{}])[0] or {}).get("splits") or []
            if splits:
                result[label] = splits[0].get("stat") or {}
        except Exception as e:
            log(f"get_situation_stats {label} error: {e}")
    return result


# -------------------------
# Dansby game grade (last game)
# -------------------------
def calculate_game_grade(game: "GameRow") -> Tuple[str, str]:
    """
    Auto-calculates a letter grade for Dansby's last game performance
    and uses the Anthropic API to generate an over-the-top one-line summary.
    Returns (grade, summary_text). Returns ("N/A", "") for DNP games.
    """
    b = game.batting or {}
    f = game.fielding or {}

    ab    = safe_int(b.get("atBats"))
    hits  = safe_int(b.get("hits"))
    hr    = safe_int(b.get("homeRuns"))
    rbi   = safe_int(b.get("rbi"))
    bb    = safe_int(b.get("baseOnBalls"))
    so    = safe_int(b.get("strikeOuts"))
    dbls  = safe_int(b.get("doubles"))
    trpls = safe_int(b.get("triples"))
    errors = safe_int(f.get("errors"))
    hbp   = safe_int(b.get("hitByPitch"))
    sf    = safe_int(b.get("sacFlies"))
    sac   = safe_int(b.get("sacBunts"))

    # DNP: no plate appearances at all
    pa = ab + bb + hbp + sf + sac
    if pa == 0:
        return "N/A", ""

    score = 35  # below-average baseline
    score += hits * 12
    score += hr * 18           # extra credit on top of hit
    score += dbls * 6          # extra credit on top of hit
    score += trpls * 9         # extra credit on top of hit
    score += rbi * 6
    score += bb * 5
    score -= so * 7
    score -= errors * 15
    if hits == 0 and ab >= 3:
        score -= 12            # 0-fer penalty

    score = max(0, min(100, score))

    if score >= 95:   grade = "A+"
    elif score >= 82: grade = "A"
    elif score >= 70: grade = "B+"
    elif score >= 58: grade = "B"
    elif score >= 46: grade = "C+"
    elif score >= 35: grade = "C"
    elif score >= 22: grade = "D"
    else:             grade = "F"

    # Build stat line for the AI prompt
    stat_line = f"{hits}-for-{ab}"
    extras = []
    if hr:     extras.append(f"{hr} HR")
    if dbls:   extras.append(f"{dbls} 2B")
    if trpls:  extras.append(f"{trpls} 3B")
    if rbi:    extras.append(f"{rbi} RBI")
    if bb:     extras.append(f"{bb} BB")
    if so:     extras.append(f"{so} K")
    if errors: extras.append(f"{errors} E")
    if extras:
        stat_line += ", " + ", ".join(extras)

    # Generate over-the-top summary via Anthropic API
    summary = _generate_grade_summary(grade, stat_line, score)
    return grade, summary


def _generate_grade_summary(grade: str, stat_line: str, score: int) -> str:
    """Calls the Anthropic API to generate a one-line over-the-top game summary."""
    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            return f"Grade {grade} — {stat_line}."
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"You are writing a one-sentence game summary for a Dansby Swanson fan newsletter. "
                        f"The tone is enthusiastic, over-the-top positive, and witty — even when the game was bad, "
                        f"find something to celebrate or frame it heroically. "
                        f"Dansby's stat line was: {stat_line}. His grade was {grade} (score {score}/100). "
                        f"Write exactly ONE punchy sentence. No intro, no explanation, just the sentence."
                    )
                }]
            },
            timeout=15,
        )
        data = response.json()
        text = (data.get("content") or [{}])[0].get("text", "").strip()
        return text if text else f"Grade {grade} — {stat_line}."
    except Exception as e:
        log(f"_generate_grade_summary error: {e}")
        return f"Grade {grade} — {stat_line}."


# -------------------------
# DNP tracker
# -------------------------
def get_dnp_count(today: date) -> int:
    """
    Counts games the Cubs played this season where Dansby was on the bench
    (active roster but did not play — isOnBench=true, empty batting/fielding stats).
    """
    try:
        start = REGULAR_SEASON_START
        url = (f"https://statsapi.mlb.com/api/v1/schedule"
               f"?sportId=1&teamId={TEAM_ID_CUBS}&startDate={start}&endDate={today}&gameType=R")
        data = fetch_json(url)
        games = [g for d in data.get("dates", []) for g in d.get("games", [])
                 if game_is_final(g)]

        dnp_count = 0
        for g in games:
            pk = g.get("gamePk")
            if not pk:
                continue
            try:
                box = fetch_boxscore(int(pk))
                for side in ("home", "away"):
                    players = (box.get("teams", {}).get(side, {}).get("players", {}) or {})
                    for _pid, pdata in players.items():
                        if pdata.get("person", {}).get("id") == SWANSON_MLBAM_ID:
                            game_status = pdata.get("gameStatus", {})
                            batting = pdata.get("stats", {}).get("batting", {})
                            fielding = pdata.get("stats", {}).get("fielding", {})
                            # DNP = on bench with no batting or fielding stats
                            if game_status.get("isOnBench") and not batting and not fielding:
                                dnp_count += 1
                                log(f"DNP: {g.get('officialDate')} pk={pk}")
            except Exception as e:
                log(f"DNP check error gamePk={pk}: {e}")
                continue
        log(f"DNP count: {dnp_count}")
        return dnp_count
    except Exception as e:
        log(f"get_dnp_count error: {e}")
        return 0

# -------------------------
# Statcast quality of contact (Savant)
# -------------------------
SAVANT_QOC_URL = (
    "https://baseballsavant.mlb.com/leaderboard/custom"
    "?year={year}&type=batter&filter=&min=q"
    "&selections=exit_velocity_avg,launch_angle_avg,barrel_batted_rate,hard_hit_percent,xba,xslg,xwoba,xobp"
    "&chart=false&x=xba&y=xba&r=no&chartType=beeswarm&csv=true"
)

def fetch_statcast_qoc(season: int) -> Tuple[Optional[dict], List[dict]]:
    """
    Fetch Dansby barrel rate and hard hit % from Baseball Savant,
    plus full SS rankings sorted by barrel rate.
    Returns (dansby_stats, ss_rankings).
    """
    try:
        import csv as _csv

        # Get qualified SS ids from MLB Stats API
        ss_url = (f"https://statsapi.mlb.com/api/v1/stats"
                  f"?stats=season&group=hitting&season={season}&sportId=1"
                  f"&position=SS&limit=100&offset=0&sortStat=onBasePlusSlugging&order=desc")
        ss_data = fetch_json(ss_url)
        ss_ids = {
            str(s.get("player",{}).get("id","")): s.get("player",{}).get("fullName","")
            for s in (ss_data.get("stats",[{}])[0].get("splits",[]))
            if safe_int(s.get("stat",{}).get("atBats",0)) >= SS_MIN_AB
        }

        url = SAVANT_QOC_URL.format(year=season)
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        text = r.text.lstrip("﻿")
        reader = _csv.DictReader(io.StringIO(text))

        dansby_stats = None
        ss_rankings = []
        reader_rows = []
        for row in reader:
            reader_rows.append(row)
        for row in reader_rows:
            pid = str(row.get("player_id",""))
            is_dansby = pid == str(SWANSON_MLBAM_ID)
            if is_dansby:
                dansby_stats = {
                    "exit_velo":  row.get("exit_velocity_avg","N/A"),
                    "launch_ang": row.get("launch_angle_avg","N/A"),
                    "barrel_pct": row.get("barrel_batted_rate","N/A"),
                    "hard_hit":   row.get("hard_hit_percent","N/A"),
                    "xba":        row.get("xba","N/A"),
                    "xslg":       row.get("xslg","N/A"),
                    "xobp":       row.get("xobp","N/A"),
                    "xwoba":      row.get("xwoba","N/A"),
                }
            if pid in ss_ids:
                ss_rankings.append({
                    "name":      ss_ids[pid],
                    "barrel":    safe_float(row.get("barrel_batted_rate",0)),
                    "hard_hit":  safe_float(row.get("hard_hit_percent",0)),
                    "exit_velo": row.get("exit_velocity_avg",""),
                    "is_dansby": is_dansby,
                })

        ss_rankings.sort(key=lambda x: x["barrel"], reverse=True)
        if not dansby_stats:
            log("fetch_statcast_qoc: Dansby not found in Savant data")

        # Calculate SS averages
        def _avg(vals):
            v = [safe_float(x) for x in vals if x and safe_float(x) > 0]
            return round(sum(v)/len(v), 1) if v else 0.0

        ss_avgs = {
            "barrel_pct": _avg([p["barrel"] for p in ss_rankings]),
            "hard_hit":   _avg([p["hard_hit"] for p in ss_rankings]),
            "exit_velo":  _avg([p["exit_velo"] for p in ss_rankings]),
            "launch_ang": _avg([r.get("launch_angle_avg","") for r in reader_rows if r.get("player_id","") in ss_ids]),
        } if ss_rankings else {}

        return dansby_stats, ss_rankings, ss_avgs
    except Exception as e:
        log(f"fetch_statcast_qoc error: {e}")
        return None, [], {}

# -------------------------
# OPS trend chart
# -------------------------
def build_ops_chart(recent_newest_first: List[GameRow], ss_ranked: Optional[List[dict]] = None) -> Optional[str]:
    """
    Builds a 30-game rolling OPS trend chart.
    Returns a base64-encoded PNG string for embedding in HTML email, or None on failure.
    """
    try:
        # Work oldest-to-newest for the chart
        games = list(reversed(recent_newest_first[:30]))
        if len(games) < 2:
            return None

        dates = []
        ops_vals = []
        cumulative = {k: 0 for k in ("atBats","hits","homeRuns","doubles","triples",
                                      "baseOnBalls","hitByPitch","sacFlies")}

        # Seed cumulative from all games outside the plot window so the chart
        # shows season-to-date OPS evolving, not a reset-to-zero at game 1.
        for g_seed in recent_newest_first[30:]:
            b_seed = g_seed.batting or {}
            for k in cumulative:
                cumulative[k] += safe_int(b_seed.get(k))

        for g in games:
            try:
                dt = date.fromisoformat((g.game_date or "")[:10])
            except Exception:
                continue
            b = g.batting or {}
            for k in cumulative:
                cumulative[k] += safe_int(b.get(k))
            ab  = cumulative["atBats"]
            h   = cumulative["hits"]
            bb  = cumulative["baseOnBalls"]
            hbp = cumulative["hitByPitch"]
            sf  = cumulative["sacFlies"]
            d   = cumulative["doubles"]
            tri = cumulative["triples"]
            hr  = cumulative["homeRuns"]
            singles = max(h - d - tri - hr, 0)
            tb = singles + 2*d + 3*tri + 4*hr
            den = ab + bb + hbp + sf
            obp = (h + bb + hbp) / den if den else 0.0
            slg = tb / ab if ab else 0.0
            dates.append(dt)
            ops_vals.append(round(obp + slg, 3))

        if len(dates) < 2:
            return None

        fig, ax = plt.subplots(figsize=(7, 3))
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#f9f9f9")

        ax.plot(dates, ops_vals, color="#1a73e8", linewidth=2.5, marker="o",
                markersize=4, markerfacecolor="#1a73e8")
        ax.fill_between(dates, ops_vals, alpha=0.08, color="#1a73e8")

        # SS median OPS reference line (dynamic from rankings)
        if ss_ranked:
            def _to_float(v):
                try:
                    s = str(v).strip()
                    return float("0" + s if s.startswith(".") else s)
                except:
                    return 0.0
            ss_ops_vals = sorted([_to_float(p.get("ops", 0)) for p in ss_ranked if p.get("ops")], reverse=True)
            ss_ops_vals = [v for v in ss_ops_vals if v > 0]
            ss_median = ss_ops_vals[len(ss_ops_vals) // 2] if ss_ops_vals else 0.720
        else:
            ss_median = 0.720
        median_label = f"SS Median OPS {fmt_avg(ss_median)}"
        ax.axhline(y=ss_median, color="#e53935", linewidth=1.2, linestyle="--", alpha=0.7,
                   label=median_label)

        ax.set_title("Dansby Swanson — Cumulative OPS (Last 30 Games)",
                     fontsize=11, fontweight="bold", pad=10)
        ax.set_ylabel("OPS", fontsize=9)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, _: f"{x:.3f}".replace("0.", ".")))
        ax.set_xlim(dates[0] - timedelta(days=1), dates[-1] + timedelta(days=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        plt.xticks(rotation=30, fontsize=8)
        plt.yticks(fontsize=8)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        buf = _io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return _base64.b64encode(buf.read()).decode("utf-8")
    except Exception as e:
        log(f"build_ops_chart error: {e}")
        return None

# -------------------------
# Email build
# -------------------------
def build_email(anchor_games: List[GameRow], recent: List[GameRow]) -> Tuple[str, str, str]:
    is_dh = len(anchor_games) > 1
    game = merge_game_rows(anchor_games)
    if is_dh:
        # Replace the individual DH game entries with the single merged game,
        # preserving the newest-first sort order of the list.
        dh_pks = {g.gamePk for g in anchor_games}
        recent_for_rolling = []
        merged_inserted = False
        for r in recent:
            if r.gamePk in dh_pks:
                if not merged_inserted:
                    recent_for_rolling.append(game)
                    merged_inserted = True
            else:
                recent_for_rolling.append(r)
    else:
        recent_for_rolling = recent
    today = date.today()
    in_st = is_spring_training(today)

    picks = pick_accolades(5)
    accolades_html = (
        "<div style='padding:10px 12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;margin-bottom:10px;'>"
        "<div style='font-weight:bold;margin-bottom:6px;'>🌟 Dansby Swanson Accolades of the Day 🌟</div>"
        "<ul style='margin:0 0 0 18px;padding:0;'>"
        + "".join(f"<li>{escape_html(p)}</li>" for p in picks) + "</ul></div>"
    )
    accolades_text = "🌟 Dansby Swanson Accolades of the Day 🌟\n\n" + "\n".join(f"- {p}" for p in picks) + "\n\n"

    statcast_qoc, ss_statcast_rankings, ss_qoc_avgs = fetch_statcast_qoc(today.year) if not in_st else (None, [], {})
    ss_ranked = get_ss_ops_ranked() if not in_st else []

    if in_st:
        st = fetch_st_cumulative_stats(today.year)
        offense_text = render_st_stats_text(st)
        offense_html = render_st_stats_html(st)
        insight: List[str] = []
    else:
        roll_rows = build_roll_rows(recent_for_rolling)
        offense_text = render_table_text(roll_rows)
        offense_html = render_table_html(roll_rows, qoc=statcast_qoc, avgs=ss_qoc_avgs)
        insight = build_daily_insight(roll_rows)
        # QOC appended after rolling table in text
        if statcast_qoc:
            q = statcast_qoc
            offense_text += (
                f"Quality of Contact:  Barrel% {q['barrel_pct']}%  "
                f"Hard Hit% {q['hard_hit']}%  Exit Velo {q['exit_velo']} mph  "
                f"Launch Angle {q['launch_ang']}°\n"
                f"Expected Stats:  xBA {q.get('xba','N/A')}  xOBP {q.get('xobp','N/A')}  "
                f"xSLG {q.get('xslg','N/A')}  xwOBA {q.get('xwoba','N/A')}\n"
            )

    # Generate OPS trend chart (regular season only)
    ops_chart_b64 = build_ops_chart(recent_for_rolling, ss_ranked=ss_ranked) if not in_st and recent_for_rolling else None

    risp_season = get_risp_avg("season")
    risp_career  = get_risp_avg("career")
    ss_ranked = get_ss_ops_ranked()
    f = game.fielding or {}
    fielding_line = f"PO {safe_int(f.get('putOuts'))}, A {safe_int(f.get('assists'))}, E {safe_int(f.get('errors'))}"
    adv = get_advanced_defense()
    fielding_season = fetch_fielding_stats() if not in_st else None
    situation_stats = get_situation_stats() if not in_st else {}
    dnp_count = get_dnp_count(today) if not in_st else 0
    if not in_st:
        dh_grades = []
        for ag in anchor_games:
            gr, gs = calculate_game_grade(ag)
            if gr != "N/A":
                save_game_grade(ag.gamePk, ag.game_date, gr)
            dh_grades.append((gr, gs))
        game_grade, grade_summary = dh_grades[0]
    else:
        dh_grades = [("N/A", "")]
        game_grade, grade_summary = "N/A", ""
    grade_tally = get_grade_tally() if not in_st else {}
    monthly_grades = get_monthly_grade_summary() if not in_st else []

    dh_label = " (DH)" if is_dh else ""
    subject = f"Dansby Swanson Digest — {game.game_date} vs {game.opponent}{dh_label}"

    # TEXT
    text = [accolades_text.rstrip(), ""]
    if insight:
        text += ["Daily Insight:"] + [f"- {b}" for b in insight] + [""]
    text += [f"Dansby Swanson — {game.game_date} vs {game.opponent}{dh_label}", "",
             "Last game defense (traditional):", f"- {fielding_line}", "",
             offense_text.rstrip(), "",
             "Runners in Scoring Position (AVG):",
             f"- Dansby Swanson (season): {risp_season}",
             f"- Dansby Swanson (career): {risp_career}",
             f"- Shawon Dunston (career): {DUNSTON_CAREER_RISP_AVG}", "",
             f"Shortstop OPS Rankings (min {SS_MIN_AB} AB):"]
    text += [f"  #{i+1} {p['name']}: {p['ops']} ({p['ab']} AB)" if not p['is_dansby'] else f"  ▶ #{i+1} {p['name']}: {p['ops']} ({p['ab']} AB) <- Dansby" for i, p in enumerate(ss_ranked)]
    text += [""]
    if is_dh:
        for idx, (gr, gs) in enumerate(dh_grades, 1):
            if gr != "N/A":
                text += [f"Game {idx} Grade: {gr}", f"  {gs}", ""]
    elif game_grade != "N/A":
        text += [f"Game Grade: {game_grade}", f"  {grade_summary}", ""]
    if grade_tally:
        grade_order = ["A+","A","B+","B","C+","C","D","F"]
        tally_parts = [f"{g}:{grade_tally[g]}" for g in grade_order if g in grade_tally]
        text += ["Season Grade Tally: " + "  ".join(tally_parts), ""]
    if monthly_grades:
        text += ["Monthly Grade Summary:"]
        for m in monthly_grades:
            tally_str = "  ".join(f"{g}:{m['tally'][g]}" for g in grade_order if g in m["tally"])
            text += [f"  {m['month']} ({m['games']}G): Avg {m['avg_grade']} ({m['avg_score']})  |  {tally_str}"]
        text += [""]
    if situation_stats:
        hl = situation_stats.get("high_leverage", {})
        lc = situation_stats.get("late_close", {})
        text += ["Situational Hitting (season):"]
        if hl:
            text += [f"  High Leverage:  AVG {hl.get('avg','N/A')}  OBP {hl.get('obp','N/A')}  OPS {hl.get('ops','N/A')}  RBI {hl.get('rbi','N/A')}"]
        if lc:
            text += [f"  Late & Close:   AVG {lc.get('avg','N/A')}  OBP {lc.get('obp','N/A')}  OPS {lc.get('ops','N/A')}  RBI {lc.get('rbi','N/A')}"]
        text += [""]
    text += [f"Days Dansby Being a Bitch: {dnp_count}", ""]

    if ss_statcast_rankings:
        text += ["SS Barrel% Rankings (qualified):"]
        for i, p in enumerate(ss_statcast_rankings):
            marker = " <- Dansby" if p["is_dansby"] else ""
            text += [f"  {'▶ ' if p['is_dansby'] else '  '}#{i+1} {p['name']}: Barrel% {p['barrel']}  Hard Hit% {p['hard_hit']}  EV {p['exit_velo']}{marker}"]
        text += [""]
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

    # Game grade HTML
    _grade_colors = {
        "A+": "#1a7a1a", "A": "#2e8b2e", "B+": "#4a9e4a", "B": "#6aaa6a",
        "C+": "#b8860b", "C": "#cc9900", "D": "#cc5500", "F": "#cc0000"
    }
    if is_dh:
        game_grade_html = ""
        for idx, (gr, gs) in enumerate(dh_grades, 1):
            if gr != "N/A":
                gc = _grade_colors.get(gr, "#555555")
                game_grade_html += (
                    f"<div style='margin:10px 0;padding:12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;'>"
                    f"<span style='font-size:18px;font-weight:bold;color:{gc};'>Game {idx} Grade: {escape_html(gr)}</span>"
                    f"<span style='margin-left:12px;font-size:13px;color:#333;font-style:italic;'>{escape_html(gs)}</span>"
                    f"</div>"
                )
    else:
        grade_color = _grade_colors.get(game_grade, "#555555")
        game_grade_html = (
            f"<div style='margin:10px 0;padding:12px;border:1px solid #ddd;border-radius:8px;background:#fafafa;'>"
            f"<span style='font-size:18px;font-weight:bold;color:{grade_color};'>Game Grade: {escape_html(game_grade)}</span>"
            f"<span style='margin-left:12px;font-size:13px;color:#333;font-style:italic;'>{escape_html(grade_summary)}</span>"
            f"</div>"
        ) if game_grade != "N/A" else ""

    # Grade tally HTML
    grade_tally_html = ""
    if grade_tally:
        grade_order = ["A+","A","B+","B","C+","C","D","F"]
        grade_colors = {
            "A+":"#1a7a1a","A":"#2e8b2e","B+":"#4a9e4a","B":"#6aaa6a",
            "C+":"#b8860b","C":"#cc9900","D":"#cc5500","F":"#cc0000"
        }
        cells = ""
        for g in grade_order:
            if g in grade_tally:
                color = grade_colors.get(g,"#555")
                cells += (f"<td align='center' style='padding:8px 12px;'>"
                         f"<div style='font-weight:bold;color:{color};font-size:16px;'>{g}</div>"
                         f"<div style='font-size:20px;font-weight:bold;'>{grade_tally[g]}</div>"
                         f"</td>")
        grade_tally_html = (
            "<h3 style='margin:10px 0 6px 0;'>Season Grade Tally</h3>"
            "<table cellpadding='4' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;'>"
            f"<tr>{cells}</tr></table>"
        )

    # Monthly grade HTML
    monthly_grade_html = ""
    if monthly_grades:
        grade_order = ["A+","A","B+","B","C+","C","D","F"]
        grade_colors = {
            "A+":"#1a7a1a","A":"#2e8b2e","B+":"#4a9e4a","B":"#6aaa6a",
            "C+":"#b8860b","C":"#cc9900","D":"#cc5500","F":"#cc0000"
        }
        header = ("<tr><th align='left'>Month</th><th>G</th><th>Avg Grade</th>"
                  + "".join(f"<th>{g}</th>" for g in grade_order if any(g in m["tally"] for m in monthly_grades))
                  + "</tr>")
        active_grades = [g for g in grade_order if any(g in m["tally"] for m in monthly_grades)]
        body_rows = ""
        for m in monthly_grades:
            color = grade_colors.get(m["avg_grade"], "#555")
            body_rows += (f"<tr><td><b>{escape_html(m['month'])}</b></td>"
                         f"<td align='center'>{m['games']}</td>"
                         f"<td align='center' style='color:{color};font-weight:bold;'>{m['avg_grade']} ({m['avg_score']})</td>"
                         + "".join(f"<td align='center'>{m['tally'].get(g, '-')}</td>" for g in active_grades)
                         + "</tr>")
        monthly_grade_html = (
            "<h3 style='margin:10px 0 6px 0;'>Monthly Grade Summary</h3>"
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;'>"
            + header + body_rows + "</table>"
        )

    # Situation stats HTML
    situation_html = ""
    if situation_stats:
        hl = situation_stats.get("high_leverage", {})
        lc = situation_stats.get("late_close", {})
        rows_html = ""
        if hl:
            rows_html += (f"<tr><td><b>High Leverage</b></td>"
                         f"<td align='center'>{hl.get('avg','N/A')}</td>"
                         f"<td align='center'>{hl.get('obp','N/A')}</td>"
                         f"<td align='center'>{hl.get('slg','N/A')}</td>"
                         f"<td align='center'>{hl.get('ops','N/A')}</td>"
                         f"<td align='center'>{hl.get('rbi','N/A')}</td>"
                         f"<td align='center'>{hl.get('plateAppearances','N/A')}</td></tr>")
        if lc:
            rows_html += (f"<tr><td><b>Late &amp; Close</b></td>"
                         f"<td align='center'>{lc.get('avg','N/A')}</td>"
                         f"<td align='center'>{lc.get('obp','N/A')}</td>"
                         f"<td align='center'>{lc.get('slg','N/A')}</td>"
                         f"<td align='center'>{lc.get('ops','N/A')}</td>"
                         f"<td align='center'>{lc.get('rbi','N/A')}</td>"
                         f"<td align='center'>{lc.get('plateAppearances','N/A')}</td></tr>")
        situation_html = (
            "<h3 style='margin:10px 0 6px 0;'>Situational Hitting (season)</h3>"
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;'>"
            "<tr><th align='left'>Split</th><th>AVG</th><th>OBP</th><th>SLG</th><th>OPS</th><th>RBI</th><th>PA</th></tr>"
            + rows_html + "</table>"
        )

    if fielding_season:
        fs = fielding_season
        fielding_season_html = (
            "<h3 style='margin:10px 0 6px 0;'>Season Fielding (SS)</h3>"
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;'>"
            "<tr><th>FLD%</th><th>PO</th><th>A</th><th>E</th><th>DP</th><th>RF/G</th><th>Inn</th></tr>"
            f"<tr>"
            f"<td align='center'><strong>{fs.get('fielding','N/A')}</strong></td>"
            f"<td align='center'>{fs.get('putOuts','N/A')}</td>"
            f"<td align='center'>{fs.get('assists','N/A')}</td>"
            f"<td align='center'>{fs.get('errors','N/A')}</td>"
            f"<td align='center'>{fs.get('doublePlays','N/A')}</td>"
            f"<td align='center'>{fs.get('rangeFactorPerGame','N/A')}</td>"
            f"<td align='center'>{fs.get('innings','N/A')}</td>"
            f"</tr></table>"
        )
    else:
        fielding_season_html = ""

    # Statcast QOC HTML
    statcast_html = ""
    if statcast_qoc:
        q = statcast_qoc
        statcast_html = (
            "<h3 style='margin:10px 0 6px 0;'>Quality of Contact (Statcast)</h3>"
            "<table cellpadding='6' cellspacing='0' border='1' style='border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;'>"
            "<tr><th>Barrel%</th><th>Hard Hit%</th><th>Exit Velo (mph)</th><th>Launch Angle (°)</th></tr>"
            f"<tr>"
            f"<td align='center'><strong>{q['barrel_pct']}%</strong></td>"
            f"<td align='center'><strong>{q['hard_hit']}%</strong></td>"
            f"<td align='center'>{q['exit_velo']}</td>"
            f"<td align='center'>{q['launch_ang']}</td>"
            f"</tr></table>"
        )

    ops_chart_html = (
        f"<h3 style='margin:10px 0 6px 0;'>OPS Trend (Last 30 Games)</h3>"
        f"<img src='data:image/png;base64,{ops_chart_b64}' "
        f"style='width:100%;max-width:700px;display:block;margin:0 0 10px 0;' alt='OPS Trend Chart'>"
    ) if ops_chart_b64 else ""

    html_body = f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.4;">
      {accolades_html}
      {insight_html}
      <h2 style="margin:0 0 8px 0;">Dansby Swanson — {escape_html(game.game_date)} vs {escape_html(game.opponent)}{escape_html(dh_label)}</h2>
      <h3 style="margin:10px 0 6px 0;">Last game defense (traditional)</h3>
      <div style="margin:0 0 10px 0;">{escape_html(fielding_line)}</div>

      {game_grade_html}
      {grade_tally_html}
      {monthly_grade_html}
      {fielding_season_html}
      {situation_html}
      {offense_html}
      <h3 style="margin:10px 0 6px 0;">Runners in Scoring Position (AVG)</h3>
      <ul style="margin:0 0 10px 18px;padding:0;">
        <li><strong>Dansby Swanson (season):</strong> {escape_html(risp_season)}</li>
        <li><strong>Dansby Swanson (career):</strong> {escape_html(risp_career)}</li>
        <li><strong>Shawon Dunston (career):</strong> {DUNSTON_CAREER_RISP_AVG}</li>
      </ul>
      <h3 style="margin:10px 0 6px 0;">Shortstop OPS Rankings (min {SS_MIN_AB} AB)</h3>
      <table cellpadding="5" cellspacing="0" border="1" style="border-collapse:collapse;border-color:#ddd;width:100%;max-width:780px;">
        <tr><th>#</th><th align="left">Player</th><th>OPS</th><th>AB</th></tr>
        {"".join(
            f"<tr style='background:{'#fffbe6' if p['is_dansby'] else 'white'};{'font-weight:bold;' if p['is_dansby'] else ''}'>"
            f"<td align='center'>{i+1}</td>"
            f"<td>{'▶ ' if p['is_dansby'] else ''}{escape_html(p['name'])}{'  ← Dansby' if p['is_dansby'] else ''}</td>"
            f"<td align='center'>{p['ops']}</td>"
            f"<td align='center'>{p['ab']}</td>"
            f"</tr>"
            for i, p in enumerate(ss_ranked)
        )}
      </table>
      {ops_chart_html}
      <h3 style='margin:10px 0 6px 0;'>Days Dansby Being a Bitch</h3>
      <div style='font-size:22px;font-weight:bold;padding:8px 12px;background:#fff8f8;border:1px solid #ddd;border-radius:8px;display:inline-block;margin-bottom:10px;'>{dnp_count}</div>
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

    subject, text_body, html_body = build_email([anchor], recent)
    subject = "[TEST EMAIL] " + subject
    to_list = TEST_TO_EMAILS or ["robertjsherman1@gmail.com"]
    send_gmail(SENDER_EMAIL, to_list, subject, text_body, html_body)
    print(f"Test email sent to: {', '.join(to_list)}")

def recalculate_all_grades() -> None:
    """
    Re-fetches boxscore stats for every game in game_grades and applies the
    current grading formula. DNP records (PA=0) are deleted; others get their
    grade updated in place without changing sent_at.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.cursor().execute(
            "SELECT gamePk, game_date FROM game_grades ORDER BY game_date"
        ).fetchall()
    finally:
        conn.close()

    print(f"Recalculating {len(rows)} game grades...")
    updated = deleted = errors = 0

    for game_pk, game_date in rows:
        try:
            box = fetch_boxscore(game_pk)
            found = find_player_in_boxscore(box, SWANSON_MLBAM_ID)
            if not found:
                conn = sqlite3.connect(DB_PATH)
                try:
                    conn.cursor().execute("DELETE FROM game_grades WHERE gamePk=?", (game_pk,))
                    conn.commit()
                finally:
                    conn.close()
                deleted += 1
                print(f"  {game_date} pk={game_pk} — removed (not in boxscore)")
                continue

            batting, fielding = found
            dummy = GameRow(gamePk=game_pk, game_date=game_date, opponent="", batting=batting, fielding=fielding)
            grade, _ = calculate_game_grade(dummy)

            conn = sqlite3.connect(DB_PATH)
            try:
                if grade == "N/A":
                    conn.cursor().execute("DELETE FROM game_grades WHERE gamePk=?", (game_pk,))
                    deleted += 1
                    print(f"  {game_date} pk={game_pk} — removed (DNP)")
                else:
                    conn.cursor().execute(
                        "UPDATE game_grades SET grade=? WHERE gamePk=?",
                        (grade, game_pk)
                    )
                    updated += 1
                    print(f"  {game_date} pk={game_pk} — {grade}")
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            log(f"recalculate_all_grades error pk={game_pk}: {e}")
            print(f"  {game_date} pk={game_pk} — ERROR: {e}")
            errors += 1

    print(f"\nDone: {updated} updated, {deleted} removed (DNP/missing), {errors} errors.")


def main() -> None:
    import sys
    if "--recalculate-grades" in sys.argv:
        recalculate_all_grades()
        return
    init_db()
    today = date.today()
    if today < EARLIEST_SEND_DATE and not TEST_MODE:
        print(f"Not yet. Starts {EARLIEST_SEND_DATE}. Today={today}")
        return
    if TEST_MODE:
        send_test_email_now()
        return
    anchor_games = pick_unsent_anchor_group(today, SEND_LOOKBACK_DAYS)
    if not anchor_games:
        print(f"No new Cubs game with Swanson in last {SEND_LOOKBACK_DAYS} days. Check dansbytracker.log.")
        return
    recent = load_recent_games_with_swanson(today, ROLLING_LOOKBACK_DAYS)
    subject, text_body, html_body = build_email(anchor_games, recent)
    send_gmail(SENDER_EMAIL, RECIPIENTS, subject, text_body, html_body)
    for ag in anchor_games:
        mark_sent(ag.gamePk)
    pks = [ag.gamePk for ag in anchor_games]
    print(f"Sent digest for gamePk={pks} to {len(RECIPIENTS)} recipients.")

if __name__ == "__main__":
    main()

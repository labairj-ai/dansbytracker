# DansbyTracker

Daily email digest tracking Dansby Swanson's performance with the Chicago Cubs. Pulls live data from MLB Stats API and Baseball Savant, grades each game A+ through F, and emails a rich HTML report each morning to a list of recipients.

---

## Features

- **Rolling batting splits** — Last game, last 10, last 30, and full season totals (AB, H, HR, RBI, AVG, OBP, SLG, OPS)
- **Game grade** — Automatic A+–F letter grade per game with an AI-generated one-liner via the Anthropic API
- **Season & monthly grade tallies** — Running scoreboard of how many A's, B's, C's, D's, and F's Dansby has earned
- **OPS trend chart** — Cumulative 30-game OPS line chart with SS median reference line, embedded as a PNG in the email
- **Statcast quality of contact** — Barrel%, Hard Hit%, Exit Velocity, Launch Angle, xBA, xOBP, xSLG, xwOBA from Baseball Savant
- **SS OPS rankings** — All qualified MLB shortstops sorted by OPS with Dansby highlighted
- **Situational splits** — High leverage and late & close AVG/OBP/OPS/RBI for the season
- **RISP** — Season and career batting average with runners in scoring position, benchmarked against Shawon Dunston's career .269
- **Season fielding stats** — FLD%, PO, A, E, DP, RF/G, innings at SS
- **Advanced defense** — OAA (Outs Above Average) and FRV (Fielding Run Value) from Baseball Savant CSV exports
- **DNP tracker** — Counts games the Cubs played where Dansby was on the bench but did not appear
- **Accolades** — Rotating snarky commentary on Dansby's offensive output, deduplicated across sends

---

## Architecture

```
dansbytracker/
├── dansbytracker_v2.py          # Main script (active)
├── dansbytracker.py             # Original version (simpler, kept for reference)
├── dansbytracker_backup_20260607.py  # Snapshot backup
├── run_dansbytracker.sh         # Shell wrapper called by launchd
├── swanson_digest.sqlite        # SQLite DB — sent games, grades, used accolades
├── fielding_run_value.csv       # FRV data exported from Baseball Savant
├── outs_above_average.csv       # OAA data exported from Baseball Savant
├── token.json                   # Gmail OAuth token (not in git)
├── credentials.json             # Gmail OAuth credentials (not in git)
└── venv/                        # Python virtual environment (not in git)
```

`dansbytracker_v2.py` is the active script. `run_dansbytracker.sh` activates the venv and runs it; launchd calls that shell script at 7 AM daily.

---

## Prerequisites

- Python 3.9+
- A Google Cloud project with the Gmail API enabled and OAuth credentials (`credentials.json`)
- An Anthropic API key (for AI-generated game grade summaries)
- macOS launchd (for scheduling) or any cron-equivalent

---

## Setup

**1. Clone and create a virtual environment**

```bash
git clone https://github.com/labairj-ai/dansbytracker.git
cd dansbytracker
python3 -m venv venv
source venv/bin/activate
pip install requests matplotlib google-auth google-auth-oauthlib google-api-python-client anthropic
```

**2. Set environment variables**

Create a `.env` file or set these in your launchd plist:

```env
SENDER_EMAIL=your-gmail@gmail.com
ANTHROPIC_API_KEY=sk-ant-...

# Optional — paths to Baseball Savant CSV exports for advanced defense
SAVANT_OAA_CSV_URL=/path/to/outs_above_average.csv
SAVANT_FRV_CSV_URL=/path/to/fielding_run_value.csv

# Optional — override SQLite DB location (default: swanson_digest.sqlite in CWD)
DANSBYTRACKER_DB_PATH=/path/to/swanson_digest.sqlite

# Test mode flags
TEST_MODE=0
FORCE_TEST_EMAIL=0
TEST_TO_EMAILS=you@example.com
```

**3. Authorize Gmail**

Place your `credentials.json` (OAuth client secret from Google Cloud Console) in the project directory, then run the script once interactively to complete the OAuth flow and generate `token.json`:

```bash
python dansbytracker_v2.py
```

Follow the browser prompt. The token is saved to `token.json` and auto-refreshed on subsequent runs.

**4. Add recipients**

Edit the `RECIPIENTS` list at the top of `dansbytracker_v2.py`.

---

## Scheduling (macOS launchd)

The included `run_dansbytracker.sh` script activates the venv and runs the tracker. Wire it to launchd with a plist in `~/Library/LaunchAgents/`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.user.dansbytracker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/ai_lab/Desktop/dansbytracker/run_dansbytracker.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SENDER_EMAIL</key>
    <string>your-gmail@gmail.com</string>
    <key>ANTHROPIC_API_KEY</key>
    <string>sk-ant-...</string>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/ai_lab/Desktop/dansbytracker/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/ai_lab/Desktop/dansbytracker/launchd_error.log</string>
</dict>
</plist>
```

Load it with:

```bash
launchctl load ~/Library/LaunchAgents/com.user.dansbytracker.plist
```

---

## Test Mode

Send a test email without marking games as sent:

```bash
TEST_MODE=1 TEST_TO_EMAILS=you@example.com SENDER_EMAIL=you@gmail.com python dansbytracker_v2.py
```

Force a test email even if no game is found (useful during off-days):

```bash
TEST_MODE=1 FORCE_TEST_EMAIL=1 TEST_TO_EMAILS=you@example.com SENDER_EMAIL=you@gmail.com python dansbytracker_v2.py
```

---

## Database

SQLite at `swanson_digest.sqlite` (excluded from git).

| Table | Purpose |
|-------|---------|
| `sent_games` | gamePk + timestamp for each digest sent — prevents duplicate sends |
| `game_grades` | Per-game letter grades with date — powers season and monthly tallies |
| `used_accolades` | Tracks which accolades have been shown — ensures rotation without repeats |

---

## Data Sources

| Source | Data |
|--------|------|
| MLB Stats API (`statsapi.mlb.com`) | Schedule, boxscores, season/career splits, RISP, fielding, SS rankings |
| Baseball Savant (`baseballsavant.mlb.com`) | Statcast quality of contact (barrel%, hard hit%, exit velo, xBA/xOBP/xSLG/xwOBA) |
| Baseball Savant CSV exports | OAA and FRV (manually downloaded and referenced via env var) |
| Anthropic API | AI-generated one-line game grade summaries |

---

## Key Constants

| Constant | Value | Notes |
|----------|-------|-------|
| `SWANSON_MLBAM_ID` | 621020 | Dansby Swanson's MLB player ID |
| `TEAM_ID_CUBS` | 112 | Chicago Cubs team ID |
| `REGULAR_SEASON_START` | 2026-03-26 | Rolling stats reset; ST games excluded after this date |
| `SEND_LOOKBACK_DAYS` | 14 | Window for finding unsent games to trigger a digest |
| `ROLLING_LOOKBACK_DAYS` | 60 | Window for pulling recent games to build rolling splits |
| `SS_MIN_AB` | 80 | Minimum at-bats to qualify in the SS OPS rankings |

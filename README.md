# DansbyTracker

Daily email digest tracking Dansby Swanson's performance with the Chicago Cubs. Pulls live data from the MLB Stats API and Baseball Savant, grades each game A+ through F, and sends a rich HTML report each morning after a Cubs game.

---

## Features

- **Rolling batting splits** — Last game, last 10, last 30, and full season totals (AB, H, HR, RBI, AVG, OBP, SLG, OPS)
- **Doubleheader support** — Both games are aggregated into a single digest with combined stats and individual game grades
- **Game grade** — Automatic A+–F letter grade per game with an AI-generated one-liner via the Anthropic API
- **Season & monthly grade tallies** — Running scoreboard of how many A's, B's, C's, D's, and F's Dansby has earned
- **OPS trend chart** — Season-to-date cumulative OPS line chart across the last 30 games with SS median reference line, embedded as a PNG in the email
- **Statcast quality of contact** — Barrel%, Hard Hit%, Exit Velocity, Launch Angle, xBA, xOBP, xSLG, xwOBA from Baseball Savant
- **SS OPS rankings** — All qualified MLB shortstops sorted by OPS with Dansby highlighted
- **Situational splits** — High leverage and late & close AVG/OBP/OPS/RBI for the season
- **RISP** — Season and career batting average with runners in scoring position, benchmarked against Shawon Dunston's career .269
- **Season fielding stats** — FLD%, PO, A, E, DP, RF/G, innings at SS
- **Advanced defense** — OAA (Outs Above Average) and FRV (Fielding Run Value) from Baseball Savant CSV exports
- **DNP tracker** — Counts games where Dansby was active but did not appear
- **Accolades** — 66 rotating snarky one-liners, deduplicated so none repeat until all have been used

---

## Repository

```
dansbytracker/
├── dansbytracker.py         # Main script
├── run_dansbytracker.sh     # Shell wrapper called by launchd
├── swanson_digest.sqlite    # SQLite DB — sent games, grades, used accolades (not in git)
├── token.json               # Gmail OAuth token (not in git)
├── credentials.json         # Gmail OAuth credentials (not in git)
└── venv/                    # Python virtual environment (not in git)
```

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
pip install requests matplotlib google-auth google-auth-oauthlib google-api-python-client
```

**2. Set environment variables**

Set these in your launchd plist or shell:

```env
SENDER_EMAIL=your-gmail@gmail.com
ANTHROPIC_API_KEY=sk-ant-...

# Optional — paths to Baseball Savant CSV exports for advanced defense stats
SAVANT_OAA_CSV_URL=/path/to/outs_above_average.csv
SAVANT_FRV_CSV_URL=/path/to/fielding_run_value.csv

# Optional — override SQLite DB location (default: swanson_digest.sqlite in CWD)
DANSBYTRACKER_DB_PATH=/path/to/swanson_digest.sqlite

# Test mode flags
TEST_MODE=0
FORCE_TEST_EMAIL=0
TEST_TO_EMAILS=you@example.com
```

The OAA and FRV CSVs are downloaded manually from [Baseball Savant](https://baseballsavant.mlb.com) and need to be refreshed periodically during the season.

**3. Authorize Gmail**

Place your `credentials.json` (OAuth client secret from Google Cloud Console) in the project directory, then run the script once interactively to complete the OAuth flow and generate `token.json`:

```bash
python dansbytracker.py
```

Follow the browser prompt. The token is saved to `token.json` and auto-refreshed on subsequent runs.

**4. Add recipients**

Edit the `RECIPIENTS` list near the top of `dansbytracker.py`.

---

## Scheduling (macOS launchd)

The included `run_dansbytracker.sh` activates the venv and runs the tracker. Wire it to launchd with a plist in `~/Library/LaunchAgents/`:

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
    <string>/path/to/dansbytracker/run_dansbytracker.sh</string>
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
  <string>/path/to/dansbytracker/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>/path/to/dansbytracker/launchd.log</string>
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
TEST_MODE=1 TEST_TO_EMAILS=you@example.com SENDER_EMAIL=you@gmail.com python dansbytracker.py
```

Force a test email even if no game is found (useful during off-days):

```bash
TEST_MODE=1 FORCE_TEST_EMAIL=1 TEST_TO_EMAILS=you@example.com SENDER_EMAIL=you@gmail.com python dansbytracker.py
```

Recalculate all historical game grades with the current formula:

```bash
python dansbytracker.py --recalculate-grades
```

---

## Database

SQLite at `swanson_digest.sqlite` (excluded from git).

| Table | Purpose |
|-------|---------|
| `sent_games` | gamePk + timestamp for each digest sent — prevents duplicate sends |
| `game_grades` | Per-game letter grades with date — powers season and monthly tallies |
| `used_accolades` | Tracks which accolades have been shown — ensures full rotation before repeats |

---

## Data Sources

| Source | Data |
|--------|------|
| MLB Stats API (`statsapi.mlb.com`) | Schedule, boxscores, season/career splits, RISP, fielding, SS rankings |
| Baseball Savant (`baseballsavant.mlb.com`) | Statcast quality of contact (barrel%, hard hit%, exit velo, xBA/xOBP/xSLG/xwOBA) |
| Baseball Savant CSV exports | OAA and FRV (manually downloaded, referenced via env var) |
| Anthropic API | AI-generated one-line game grade summaries |

---

## Key Constants

| Constant | Value | Notes |
|----------|-------|-------|
| `SWANSON_MLBAM_ID` | 621020 | Dansby Swanson's MLB player ID |
| `TEAM_ID_CUBS` | 112 | Chicago Cubs team ID |
| `REGULAR_SEASON_START` | 2026-03-26 | Rolling stats reset; spring training games excluded after this date |
| `SEND_LOOKBACK_DAYS` | 14 | Window for finding unsent games to trigger a digest |
| `ROLLING_LOOKBACK_DAYS` | 60 | Window for pulling recent games to build rolling splits and the OPS chart |
| `SS_MIN_AB` | 80 | Minimum at-bats to qualify in the SS OPS rankings |

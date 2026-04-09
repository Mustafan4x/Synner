# Synner

Automated LinkedIn job application bot that searches for entry/junior-level positions across 4 role categories (SWE, Fullstack, ML/AI, Data Engineering), selects the correct resume, fills out Easy Apply forms using GPT-4o-mini for screening questions, and submits applications unattended.

## What It Does

- Searches LinkedIn for jobs across 16 DFW-area locations + Remote
- Filters out senior/staff/lead positions automatically
- Picks the right resume PDF based on job category
- Answers screening questions using GPT-4o-mini + your resume data
- Logs every application to CSV for tracking
- Includes a web dashboard to monitor progress in real time

## Prerequisites

- **Python 3.11+**
- **Google Chrome** installed
- **OpenAI API key** (for GPT-4o-mini screening answers)
- **LinkedIn account** (Premium recommended for Easy Apply access)
- **Resume PDFs** at `~/Documents/resumes/pdfs/`:
  - `Resume_SWE.pdf`
  - `Resume_FS.pdf`
  - `Resume_MLAI.pdf`
  - `Resume_DE.pdf`

## Setup

```bash
# 1. Clone and enter the project
cd ~/src/Synner

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install setuptools (required for Python 3.12+)
pip install setuptools

# 5. Add your OpenAI API key to config.yaml
#    Open config.yaml and replace "sk-..." with your actual key
nano config.yaml
```

## First Run (LinkedIn Login)

The first time you run Synner, it opens a Chrome window so you can log into LinkedIn manually. Your session is saved in `./chrome_profile/` so you only need to do this once.

```bash
# Run in dry-run mode first to log in and verify everything works
python3 run.py --dry-run
```

1. Chrome opens — log into LinkedIn manually
2. Once logged in, Synner starts searching and matching jobs
3. In dry-run mode it will NOT submit any applications — it just shows what it would do

## Usage

```bash
# Run all 4 categories (SWE, Fullstack, ML/AI, Data Engineering)
python3 run.py

# Run a single category
python3 run.py --category SWE
python3 run.py --category FS
python3 run.py --category MLAI
python3 run.py --category DE

# Dry run — search and match but don't submit
python3 run.py --dry-run

# Headless — run without visible browser window
python3 run.py --headless

# Combine flags
python3 run.py --category SWE --dry-run --headless
```

## Web Dashboard

Synner includes a Flask dashboard for monitoring applications in real time.

```bash
# Launch the dashboard (runs on http://127.0.0.1:5000)
python3 -m applier.dashboard
```

**Dashboard pages:**
- **Dashboard** (`/`) — Live activity feed, stats cards, category progress, success rate
- **History** (`/history`) — Searchable/sortable table of all past applications with filters and CSV export
- **Controls** (`/controls`) — Start/stop the bot, select categories, toggle dry-run/headless
- **Settings** (`/settings`) — Edit config.yaml through the UI (API key, delays, limits)

## Configuration

All settings are in `config.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `openai_api_key` | `sk-...` | Your OpenAI API key (required) |
| `linkedin_profile_dir` | `./chrome_profile` | Chrome profile for LinkedIn session |
| `resume_dir` | `~/Documents/resumes/pdfs` | Directory containing resume PDFs |
| `max_applications_per_session` | `100` | Max total applications per run |
| `max_per_category` | `30` | Max applications per category per run |
| `delay_min_seconds` | `30` | Min delay between applications (seconds) |
| `delay_max_seconds` | `60` | Max delay between applications (seconds) |
| `search_delay_min_seconds` | `120` | Min delay between searches (seconds) |
| `search_delay_max_seconds` | `300` | Max delay between searches (seconds) |
| `headless` | `false` | Run Chrome without visible window |

Your resume data for screening questions is in `plain_text_resume.yaml`. Update it if your experience, projects, or skills change.

## Resume Categories

| Category | Resume File | Search Keywords |
|----------|-------------|-----------------|
| SWE | `Resume_SWE.pdf` | software engineer intern, junior software engineer, etc. |
| FS | `Resume_FS.pdf` | fullstack developer, full stack engineer, etc. |
| MLAI | `Resume_MLAI.pdf` | machine learning intern, AI engineer, data scientist, etc. |
| DE | `Resume_DE.pdf` | data engineer, ETL developer, data pipeline engineer, etc. |

## Filters

**Title blacklist** — automatically skips jobs with these in the title:
- senior, sr., staff, lead, principal, manager, director, VP, "head of"
- "architect" (unless preceded by "junior" or "associate")

**Description blacklist** — skips jobs requiring 5+ years of experience.

## Output

**Console** — real-time color-coded log:
```
[2026-04-08 14:32:01] [SWE]  APPLIED  Junior Software Engineer @ Capital One (Dallas, TX)
[2026-04-08 14:32:45] [SWE]  SKIPPED  Senior SWE @ Google (title blacklist)
```

**CSV** — `applications.csv` logs every application with: date, category, company, title, location, status, reason, LinkedIn URL.

**Session summary** — printed at the end of each run:
```
Session complete:
  SWE:  23 applied, 4 skipped, 1 failed
  FS:   18 applied, 6 skipped, 0 failed
  Total: 41 applied, 10 skipped, 1 failed
```

## Project Structure

```
Synner/
  run.py                     # Entry point — python3 run.py
  config.yaml                # User settings (API key, delays, limits)
  plain_text_resume.yaml     # Resume data for GPT screening answers
  requirements.txt           # Python dependencies
  applier/
    __init__.py              # Package with lazy imports
    config.py                # Config + resume YAML loading
    filters.py               # Title/description blacklist filtering
    logger.py                # Console + CSV logging
    llm.py                   # GPT-4o-mini screening question answers
    form_filler.py           # Form field detection + filling
    linkedin.py              # LinkedIn search + Easy Apply automation
    dashboard/
      app.py                 # Flask web dashboard
      __main__.py            # python -m applier.dashboard entry point
      static/styles.css      # Dashboard styling
      templates/             # HTML templates (dashboard, history, controls, settings)
  tests/
    test_filters.py          # Filter unit tests
    test_config.py           # Config loading tests
    test_llm.py              # LLM integration tests (mocked)
    test_logger.py           # Logger tests
    MANUAL_QA.md             # Manual testing checklist
  chrome_profile/            # Persisted browser session (gitignored)
  applications.csv           # Application log (gitignored)
```

## Running Tests

```bash
pytest tests/ -v
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: distutils` | `pip install setuptools` (needed for Python 3.12+) |
| Chrome doesn't open | Make sure Google Chrome is installed |
| `ConfigError: missing key` | Check `config.yaml` has all required fields |
| LinkedIn login expired | Delete `chrome_profile/` and run again to re-login |
| Bot gets rate-limited | Increase delay settings in `config.yaml` |
| `openai.AuthenticationError` | Check your API key in `config.yaml` |

## Rate Limiting

Synner uses randomized delays to avoid detection:
- 30-60 seconds between applications
- 2-5 minutes between searches
- Max 100 applications per session (30 per category)
- Minimum 4 hours between sessions (manual enforcement)

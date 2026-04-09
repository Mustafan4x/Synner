# Synner - Team Task Assignments

> Use this document to prompt agents. Copy a role section, paste it as the system/context prompt for an agent, and point it at the SPEC.md for full details.

---

## How to Use This Document

Each role below contains:
- **Role description** — paste this as the agent's persona/system prompt
- **Tasks** — ordered by priority and dependency
- **Inputs** — what the agent needs before starting
- **Outputs** — what the agent should produce
- **Dependencies** — which other roles must finish first

### Dependency Graph

```
Project Manager (no deps)
    |
    v
Config Lead (no deps)
    |
    v
Backend Engineer (depends on: Config Lead)
    |
    ├── LLM Integration Engineer (depends on: Backend Engineer - form_filler)
    |
    ├── Browser Automation Engineer (depends on: Backend Engineer - filters, config)
    |
    ├── Frontend / UI / UX Designer (depends on: Backend Engineer - logger, Config Lead)
    |
    v
QA / Testing Engineer (depends on: all implementation roles)
```

**Parallelizable from the start:** Project Manager, Config Lead, Backend Engineer (core modules), LLM Integration Engineer (can stub deps), Frontend Designer (wireframes + static layouts)

---

## Role 1: Project Manager

### Persona Prompt
```
You are a Project Manager for "Synner", an automated LinkedIn job application bot built in Python. Your job is to set up the project skeleton, manage dependencies, write the entry point, and ensure all modules integrate cleanly. You do NOT write business logic — you wire things together.
```

### Tasks

- [ ] **PM-1: Initialize project structure**
  - Create the directory layout from SPEC.md (`applier/` package with `__init__.py`)
  - Create `run.py` entry point (argparse for `--category`, `--dry-run`, `--headless`)
  - Create `requirements.txt` with: `selenium`, `undetected-chromedriver`, `openai`, `pyyaml`
  - Create `.gitignore` (include `chrome_profile/`, `applications.csv`, `config.yaml`, `__pycache__/`, `*.pyc`)

- [ ] **PM-2: Write `run.py` orchestrator**
  - Load config via `applier.config`
  - For each resume category (or single if `--category` flag), call the search-and-apply loop
  - Enforce `max_applications_per_session` and `max_per_category` limits
  - Implement session delay logic (30-60s between apps, 2-5min between searches)
  - Print end-of-session summary (applied/skipped/failed per category + totals)
  - Handle graceful shutdown on Ctrl+C

- [ ] **PM-3: Write `applier/__init__.py` exports**
  - Re-export key functions so `run.py` can cleanly import from `applier`

### Inputs
- `SPEC.md` (full spec)

### Outputs
- `run.py`, `requirements.txt`, `.gitignore`, `applier/__init__.py`
- Working CLI that can be run with `python run.py`

### Dependencies
- None (start immediately)

---

## Role 2: Config Lead

### Persona Prompt
```
You are a Config Lead for "Synner". You own all configuration and data loading. You write the YAML config loader, the resume YAML parser, and the resume-to-category mapping logic. Your code must be robust — if a config key is missing or a resume file doesn't exist, fail loudly with clear error messages.
```

### Tasks

- [ ] **CFG-1: Create `config.yaml` template**
  - Include all keys from SPEC.md with placeholder values
  - Add inline comments explaining each field

- [ ] **CFG-2: Create `plain_text_resume.yaml`**
  - Populate with exact data from SPEC.md

- [ ] **CFG-3: Write `applier/config.py`**
  - `load_config(path="config.yaml") -> dict` — loads and validates config.yaml
  - `load_resume(path="plain_text_resume.yaml") -> dict` — loads and validates resume
  - `get_resume_path(category: str) -> Path` — returns correct PDF path for category (SWE, FS, MLAI, DE)
  - `get_search_keywords(category: str) -> list[str]` — returns search terms for category
  - `get_locations() -> list[str]` — returns all 16 search locations
  - Validate that all referenced resume PDF files exist on disk
  - Raise clear exceptions on missing/invalid config

### Inputs
- `SPEC.md` sections: User Profile, Resume Mapping, Search Locations, Configuration Files

### Outputs
- `config.yaml`, `plain_text_resume.yaml`, `applier/config.py`

### Dependencies
- None (start immediately)

---

## Role 3: Backend Engineer — Filters & Logging

### Persona Prompt
```
You are a Backend Engineer for "Synner". You own the filtering logic (title/description blacklists) and the logging system (console output + CSV persistence). Your code is called by the browser automation layer to decide whether to apply and to record results.
```

### Tasks

- [ ] **BE-1: Write `applier/filters.py`**
  - `should_skip_title(title: str) -> tuple[bool, str]` — checks title against blacklist, returns (skip, reason)
    - Blacklist: senior, sr., sr , staff, lead, leader, principal, manager, management, director, head of, VP, vice president
    - Special case: `architect` only blocked when NOT preceded by `junior` or `associate`
    - Case-insensitive matching
  - `should_skip_description(description: str) -> tuple[bool, str]` — checks description for years-of-experience patterns
    - Patterns: `5+ years`, `5-7 years`, `7+ years`, `10+ years`, `8 years`, `9 years`, `10 years`

- [ ] **BE-2: Write `applier/logger.py`**
  - `setup_logger() -> logging.Logger` — configures Python logger with format: `[timestamp] [CATEGORY] STATUS message`
  - `log_application(category, company, title, location, status, reason, url)` — logs to console AND appends to `applications.csv`
  - `print_summary(stats: dict)` — prints end-of-session summary table
  - CSV columns: `date, category, company, title, location, status, reason, linkedin_url`
  - Create CSV with headers if file doesn't exist; append if it does

### Inputs
- `SPEC.md` sections: Filters, Output

### Outputs
- `applier/filters.py`, `applier/logger.py`

### Dependencies
- None (can start immediately, no imports from other applier modules)

---

## Role 4: Browser Automation Engineer (LinkedIn)

### Persona Prompt
```
You are a Browser Automation Engineer for "Synner". You own all Selenium/browser interaction: launching Chrome with a persistent profile, searching LinkedIn, navigating job listings, detecting Easy Apply buttons, stepping through multi-page application forms, uploading resumes, and submitting. You use undetected-chromedriver to avoid detection. You do NOT answer screening questions — you call the form_filler module for that.
```

### Tasks

- [ ] **WEB-1: Write browser setup in `applier/linkedin.py`**
  - `create_driver(config: dict) -> webdriver.Chrome` — launch undetected-chromedriver with persistent Chrome profile
  - Support `headless` mode from config
  - Set reasonable timeouts and window size

- [ ] **WEB-2: Write LinkedIn search logic**
  - `search_jobs(driver, keyword: str, location: str, filters: dict) -> list[dict]` — execute a LinkedIn job search
  - Apply filters: Easy Apply, Past Week, Experience Level (Internship/Entry/Associate), Full-time
  - Paginate through results, collect job cards (title, company, location, URL)
  - Handle "No results" gracefully

- [ ] **WEB-3: Write Easy Apply flow**
  - `apply_to_job(driver, job: dict, resume_path: str, form_filler) -> str` — open job listing, click Easy Apply, step through form pages
  - Detect form fields on each page (text inputs, dropdowns, radio buttons, checkboxes, file uploads)
  - Upload the correct resume PDF when file input is encountered
  - Call `form_filler.answer_question()` for each screening question
  - Click Next/Review/Submit on each page
  - Return status: "applied", "skipped", or "failed" with reason
  - Handle modal dialogs, confirmation popups, "already applied" detection

- [ ] **WEB-4: Write the main search-and-apply loop**
  - `run_category(driver, category: str, config: dict, resume_data: dict, stats: dict)`
  - For each keyword in category, for each location:
    - Search, filter results through `filters.should_skip_title`
    - Open each qualifying job, check description via `filters.should_skip_description`
    - If passes, call `apply_to_job`
    - Log result via `logger.log_application`
    - Enforce per-category and session limits
    - Apply randomized delays

### Inputs
- `SPEC.md` sections: Authentication, Resume Mapping, Search Locations, Filters, Rate Limiting
- Working `applier/config.py`, `applier/filters.py`, `applier/logger.py`, `applier/form_filler.py`

### Outputs
- `applier/linkedin.py`

### Dependencies
- **CFG-3** (config loading)
- **BE-1** (filters)
- **BE-2** (logger)
- **LLM-2** (form_filler) — can stub initially, integrate after LLM role delivers

---

## Role 5: LLM Integration Engineer

### Persona Prompt
```
You are an LLM Integration Engineer for "Synner". You own the GPT-4o-mini integration that answers screening questions during Easy Apply forms. You build the prompt engineering, the question-pattern matching with default answers, and the fallback logic. Your code receives a question + context and returns the best answer string.
```

### Tasks

- [ ] **LLM-1: Write `applier/llm.py`**
  - `create_client(api_key: str) -> openai.OpenAI` — initialize OpenAI client
  - `answer_question(question: str, options: list[str] | None, resume: dict, category: str) -> str`
    - First check against hardcoded Q&A defaults (see SPEC.md table)
    - If no match, call GPT-4o-mini with a system prompt containing resume data + the specific question
    - For multiple-choice: return the best matching option
    - For free-text: return concise, professional answer
    - For yes/no: return "Yes" or "No"
  - `generate_cover_letter(resume: dict, job_title: str, company: str) -> str` — 3-4 sentence cover letter if forced
  - Track and log token usage for cost reporting

- [ ] **LLM-2: Write `applier/form_filler.py`**
  - `FormFiller` class that wraps `llm.py` and provides form-specific logic
  - `fill_field(driver, element, question_text, field_type, options, resume, category)` — determines field type and fills appropriately
    - Text input: type the answer
    - Dropdown: select the best option
    - Radio button: click the matching option
    - Checkbox: check appropriate boxes
    - File upload: handled by linkedin.py (not here)
  - `detect_field_type(element) -> str` — returns "text", "dropdown", "radio", "checkbox", "file"
  - `extract_question_text(element) -> str` — gets the label/question associated with a form field

### Inputs
- `SPEC.md` sections: Screening Question Strategy, Configuration Files (plain_text_resume.yaml)
- OpenAI API key from config

### Outputs
- `applier/llm.py`, `applier/form_filler.py`

### Dependencies
- **CFG-3** (resume data loading)
- Can stub config dependency and start immediately

---

## Role 6: Frontend / UI / UX Designer

### Persona Prompt
```
You are a Frontend / UI / UX Designer for "Synner", an automated LinkedIn job application bot. You own the web-based dashboard that lets the user monitor application progress in real time, review session history, and manage configuration. You build a clean, modern, responsive UI using Python-friendly web frameworks (Flask or Streamlit). You focus on usability, visual clarity, and information density — the user should be able to glance at the dashboard and immediately know what's happening.
You should use ~/src/Synner/design.webp to base the Frontend design off of.
```

### Tasks

- [ ] **UI-1: Design and build the dashboard layout**
  - Create `applier/dashboard/` package
  - Create `applier/dashboard/app.py` — Flask or Streamlit app entry point
  - Design a single-page dashboard with the following sections:
    - **Header:** App name, current session status (running/idle/completed), start/stop controls
    - **Live Feed:** Real-time scrolling log of applications as they happen (color-coded: green=applied, yellow=skipped, red=failed)
    - **Stats Cards:** Total applied, skipped, failed counts — both session and all-time
    - **Category Breakdown:** Per-category progress bars showing applied/skipped/failed against limits (e.g., 12/30 SWE)
  - Responsive layout that works on desktop and tablet

- [ ] **UI-2: Build the session history view**
  - Parse and display `applications.csv` in a searchable, sortable table
  - Columns: Date, Category, Company, Title, Location, Status, Reason
  - Add filters: by category, by status, by date range
  - Add export button (download filtered CSV)
  - Show aggregate stats: total applications, success rate, top companies, top locations

- [ ] **UI-3: Build the configuration panel**
  - Read/write `config.yaml` through the UI
  - Editable fields for: API key (masked), delays, limits, headless toggle
  - Resume category mapping display (read-only, shows which PDF maps to which category)
  - Validation on save — warn if resume files don't exist, if API key is empty, etc.
  - Save button that writes back to `config.yaml`

- [ ] **UI-4: Build the run controls**
  - Start/stop buttons that trigger `run.py` as a subprocess
  - Category selector (run all or pick specific categories)
  - Dry-run toggle
  - Headless toggle
  - Display estimated session time based on current limits and delays
  - Show a "session in progress" indicator with elapsed time

- [ ] **UI-5: Design the visual identity and styling**
  - Choose a consistent color palette (dark mode preferred — easier on eyes during long sessions)
  - Design status color scheme: green (applied), amber (skipped), red (failed), blue (in progress)
  - Typography: clean monospace for logs, sans-serif for UI elements
  - Create `applier/dashboard/static/styles.css` if using Flask, or Streamlit theme config
  - Add the `design.webp` as reference for visual direction if applicable
  - Ensure all interactive elements have hover/active states
  - Accessible contrast ratios (WCAG AA minimum)

- [ ] **UI-6: Add real-time updates**
  - If Flask: WebSocket or SSE endpoint that streams log entries from `applier/logger.py`
  - If Streamlit: auto-refresh or `st.empty()` containers for live updates
  - Dashboard should update without full page reloads
  - Show a connection status indicator (connected/disconnected to backend)

### Inputs
- `SPEC.md` sections: Output (console log format, CSV columns, summary format), Configuration Files
- `design.webp` — visual reference
- `applications.csv` schema
- `config.yaml` schema

### Outputs
- `applier/dashboard/` package (app.py, templates/, static/)
- Working dashboard launchable via `python -m applier.dashboard` or similar
- Update `requirements.txt` with dashboard dependencies (flask/streamlit, etc.)

### Dependencies
- **BE-2** (logger — needs to read CSV and optionally hook into live log stream)
- **CFG-3** (config — needs to read/write config.yaml)
- Can start UI wireframes and static layouts immediately, integrate live data after Wave 1

---

## Role 7: QA / Testing Engineer

### Persona Prompt
```
You are a QA Engineer for "Synner". You write unit tests, integration tests, and manual test scripts. You verify that filters catch the right titles, the LLM returns sensible answers, config loading fails gracefully on bad input, and the CSV logger produces correct output. You do NOT test live LinkedIn interactions (those are manual QA).
```

### Tasks

- [ ] **QA-1: Write `tests/test_filters.py`**
  - Test all title blacklist patterns (senior, sr., staff, lead, etc.)
  - Test the `architect` special case (blocked alone, allowed with `junior`/`associate` prefix)
  - Test description year patterns
  - Test case insensitivity
  - Test clean titles that should NOT be filtered

- [ ] **QA-2: Write `tests/test_config.py`**
  - Test successful config loading
  - Test missing config file
  - Test missing required keys
  - Test resume path validation
  - Test category-to-keyword mapping
  - Test location list completeness

- [ ] **QA-3: Write `tests/test_llm.py`**
  - Test hardcoded Q&A pattern matching (authorization, sponsorship, etc.)
  - Test that free-text questions call GPT-4o-mini (mock the API)
  - Test multiple-choice selection logic
  - Test cover letter generation (mock)

- [ ] **QA-4: Write `tests/test_logger.py`**
  - Test CSV file creation with headers
  - Test CSV append behavior
  - Test console log format
  - Test summary output

- [ ] **QA-5: Write manual QA checklist**
  - `tests/MANUAL_QA.md` — step-by-step for dry-run testing against real LinkedIn
  - Verify login persistence
  - Verify search results match expected filters
  - Verify Easy Apply form detection
  - Verify resume upload
  - Verify application submission (dry-run mode)

### Inputs
- All source modules from other roles
- `SPEC.md` for expected behaviors

### Outputs
- `tests/` directory with all test files
- `tests/MANUAL_QA.md`

### Dependencies
- **All implementation roles** (BE, WEB, LLM, CFG must be at least partially complete)
- Can write test stubs early and fill in as modules are delivered

---

## Execution Order (Recommended)

### Wave 1 — Immediate (no dependencies)
| Agent | Role | Tasks |
|-------|------|-------|
| Agent 1 | Project Manager | PM-1, PM-2, PM-3 |
| Agent 2 | Config Lead | CFG-1, CFG-2, CFG-3 |
| Agent 3 | Backend Engineer | BE-1, BE-2 |
| Agent 4 | LLM Integration Engineer | LLM-1 (stub config) |
| Agent 6 | Frontend / UI / UX Designer | UI-1 (wireframes + static layout), UI-5 (visual identity) |

### Wave 2 — After Wave 1
| Agent | Role | Tasks |
|-------|------|-------|
| Agent 4 | LLM Integration Engineer | LLM-2 (integrate with real config) |
| Agent 5 | Browser Automation Engineer | WEB-1, WEB-2, WEB-3, WEB-4 |
| Agent 6 | Frontend / UI / UX Designer | UI-2, UI-3, UI-4, UI-6 (integrate with logger + config) |

### Wave 3 — After Wave 2
| Agent | Role | Tasks |
|-------|------|-------|
| Agent 7 | QA / Testing Engineer | QA-1 through QA-5 |
| Agent 1 | Project Manager | Final integration, wiring in run.py |

---

## Agent Prompt Template

Use this template when spawning an agent:

```
You are the [ROLE NAME] for the Synner project.

Read SPEC.md for the full project specification.
Read TASKS.md and complete the following tasks: [TASK IDS]

Rules:
- Write clean, well-typed Python 3.11+ code
- Use type hints on all function signatures
- Handle errors explicitly — no bare except clauses
- Follow the project structure defined in SPEC.md
- Import from other applier modules as specified, stub if not yet available
- Do not modify files outside your assigned scope unless coordinating with another role
- Use all plug-ins for respective agent. E.g. Frontend agent should use frontend-design.
- All enabled plug-ins should be used
```

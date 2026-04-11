# Synner - Automated LinkedIn Job Application Bot

## Overview

Automated job application tool that searches LinkedIn for entry/junior level positions across 4 role categories, selects the correct resume, fills out Easy Apply forms using GPT-4o-mini for screening questions, and submits applications unattended.

## User Profile

- **Name:** *(set in plain_text_resume.yaml)*
- **Email:** *(set in plain_text_resume.yaml)*
- **Phone:** *(set in plain_text_resume.yaml)*
- **LinkedIn:** *(set in plain_text_resume.yaml)*
- **GitHub:** *(set in plain_text_resume.yaml)*
- **University:** *(set in plain_text_resume.yaml)*
- **Location:** *(set in plain_text_resume.yaml)*
- **Work Authorization:** Yes, authorized to work in the US
- **Willing to relocate:** Within DFW metroplex
- **LinkedIn Premium:** Yes

## Resume Mapping

| Category | File | Search Keywords |
|----------|------|-----------------|
| SWE | `~/Documents/resumes/pdfs/Resume_SWE.pdf` | `software engineer intern`, `junior software engineer`, `software developer entry level`, `associate software engineer`, `software engineer I`, `software engineer new grad` |
| Fullstack | `~/Documents/resumes/pdfs/Resume_FS.pdf` | `fullstack developer`, `full stack engineer`, `junior web developer`, `fullstack engineer entry level`, `full stack developer intern` |
| ML/AI | `~/Documents/resumes/pdfs/Resume_MLAI.pdf` | `machine learning intern`, `AI engineer entry level`, `data scientist junior`, `ML engineer intern`, `machine learning engineer new grad`, `data science intern` |
| Data Engineer | `~/Documents/resumes/pdfs/Resume_DE.pdf` | `data engineer entry level`, `junior data engineer`, `ETL developer`, `data engineer intern`, `data pipeline engineer`, `data engineer I` |

## Search Locations

15 DFW-area cities plus remote:

- Dallas, TX
- Fort Worth, TX
- Arlington, TX
- Corsicana, TX
- Plano, TX
- Frisco, TX
- Irving, TX
- Richardson, TX
- Euless, TX
- Carrollton, TX
- McKinney, TX
- Denton, TX
- Garland, TX
- Grand Prairie, TX
- Allen, TX
- Addison, TX
- Remote

## Filters

### Include
- Experience level: Internship, Entry level, Associate
- Job type: Full-time
- Easy Apply only
- Posted within: Past week

### Exclude (title blacklist)
Skip any job whose title contains (case-insensitive):
- `senior`, `sr.`, `sr `
- `staff`
- `lead`, `leader`
- `principal`
- `manager`, `management`
- `director`
- `architect` (when not preceded by `junior` or `associate`)
- `head of`
- `VP`, `vice president`

### Exclude (requirements blacklist)
Skip any job whose description contains:
- `5+ years`, `5-7 years`, `7+ years`, `10+ years`
- `8 years`, `9 years`, `10 years`

## Screening Question Strategy

GPT-4o-mini answers all screening questions using data from `plain_text_resume.yaml`.

### Common Q&A defaults
| Question pattern | Answer |
|-----------------|--------|
| Authorized to work in the US? | Yes |
| Require sponsorship? | No |
| Years of experience with [language/tool]? | Derive from resume (Python: 2, TypeScript: 2, SQL: 2, etc.) |
| Willing to relocate? | Yes, within DFW |
| Available start date? | Flexible / Immediately |
| Desired salary? | Open to discussion / competitive |
| How did you hear about this role? | LinkedIn |
| Why are you interested? | Generate 2-3 sentences from resume data relevant to the specific role |
| Describe a relevant project | Pull from AdrenalineAI or SpotMe depending on role category |
| Education level? | Bachelor's (in progress) |
| GPA? | 3.7 |
| Cover letter | Not required for Easy Apply; if forced, generate 3-4 sentences from resume |

## Rate Limiting

- **Delay between applications:** 30-60 seconds (randomized)
- **Delay between searches:** 2-5 minutes (randomized)
- **Max applications per session:** 100
- **Max applications per role category per session:** 30
- **Cool-down between sessions:** Minimum 4 hours

## Authentication

- Browser-based: bot opens Chrome, user logs into LinkedIn manually on first run
- Session cookies are persisted in a local Chrome profile so login is one-time
- No LinkedIn credentials stored in config files

## Output

### Console log (real-time)
```
[2026-04-08 14:32:01] [SWE]  APPLIED  Junior Software Engineer @ Capital One (Dallas, TX)
[2026-04-08 14:32:45] [SWE]  SKIPPED  Senior SWE @ Google (title blacklist)
[2026-04-08 14:33:12] [MLAI] APPLIED  ML Engineer Intern @ Toyota (Plano, TX)
[2026-04-08 14:33:50] [DE]   FAILED   Data Engineer I @ ATT (form error: required field missing)
```

### applications.csv (persistent log)
Columns: `date`, `category`, `company`, `title`, `location`, `status`, `reason`, `linkedin_url`

### summary (end of session)
```
Session complete:
  SWE:  23 applied, 4 skipped, 1 failed
  FS:   18 applied, 6 skipped, 0 failed
  MLAI: 12 applied, 3 skipped, 2 failed
  DE:   15 applied, 5 skipped, 1 failed
  Total: 68 applied, 18 skipped, 4 failed
  Cost: ~$1.02 (GPT-4o-mini tokens)
```

## Configuration Files

### config.yaml
```yaml
openai_api_key: "sk-..."
linkedin_profile_dir: "./chrome_profile"
resume_dir: "~/Documents/resumes/pdfs"
max_applications_per_session: 100
max_per_category: 30
delay_min_seconds: 30
delay_max_seconds: 60
search_delay_min_seconds: 120
search_delay_max_seconds: 300
headless: false  # set true to run without visible browser
```

### plain_text_resume.yaml
```yaml
personal:
  name: "Your Name"
  email: "your.email@example.com"
  phone: "555-555-0100"
  location: "Your City, ST"
  linkedin: "linkedin.com/in/your-profile"
  github: "github.com/your-username"

education:
  school: "Your University"
  degree: "Bachelor of Science in Computer Science"
  graduation: "May 2027"
  coursework:
    - Data Structures and Algorithms
    - Object-Oriented Programming
    - Software Engineering
    - Operating Systems
    - Artificial Intelligence
    - Fundamentals of Machine Learning

experience:
  - title: "Software Engineering Intern"
    company: "Acme Corp"
    location: "Your City, ST"
    dates: "May 2025 - Aug 2025"
    bullets:
      - "Developed internal inventory tracking scripts in Python"
      - "Designed and implemented a relational database schema"
      - "Built automated reporting tools generating daily summaries"

projects:
  - name: "AdrenalineAI"
    tech: "Python, Streamlit, XGBoost, BeautifulSoup, Pandas"
    bullets:
      - "ML-powered UFC fight prediction platform deployed to Streamlit Community Cloud"
      - "Trained XGBoost classifier achieving 81% cross-validation accuracy on 626 historical fights using 31 engineered features"
      - "Integrated live betting odds from The Odds API and implemented GroupKFold validation to prevent data leakage"
      - "Built 1,850-line Streamlit web app with radar charts, confidence bars, and interactive fighter comparisons"
  - name: "SpotMe"
    tech: "TypeScript, React Native, Expo, SQLite, Zustand"
    bullets:
      - "Cross-platform fitness tracking mobile app with file-based routing and offline-first SQLite persistence"
      - "Normalized 8-table database schema with WAL mode, foreign key constraints, and cascading deletes"
      - "CSV import pipeline parsing 6+ data formats with batch insertion and import history tracking"
      - "Analytics dashboard with volume trends, PR timelines, and linear regression trend analysis"

skills:
  languages: ["Python", "TypeScript", "JavaScript", "C/C++", "SQL", "HTML/CSS"]
  frameworks: ["React Native", "Expo", "Streamlit", "Node.js"]
  tools: ["Git", "GitHub", "Linux", "SQLite", "PostgreSQL", "Docker"]
  libraries: ["Pandas", "NumPy", "scikit-learn", "XGBoost", "Zustand", "Jest", "BeautifulSoup"]

years_of_experience:
  Python: 2
  TypeScript: 2
  JavaScript: 2
  SQL: 2
  "C/C++": 2
  React Native: 1
  Git: 2
  Linux: 2
  Docker: 1
```

## Tech Stack

- **Language:** Python 3.11+
- **Browser automation:** Selenium with undetected-chromedriver
- **LLM:** OpenAI GPT-4o-mini via openai Python SDK
- **Config:** PyYAML
- **Logging:** Python logging + CSV writer
- **Dependencies:** selenium, undetected-chromedriver, openai, pyyaml

## Project Structure

```
~/src/Synner/
  SPEC.md                    # this file
  config.yaml                # user settings (API key, delays, limits)
  plain_text_resume.yaml     # structured resume data for LLM
  run.py                     # entry point - python run.py
  applier/
    __init__.py
    linkedin.py              # LinkedIn search + Easy Apply automation
    form_filler.py           # form detection + field filling logic
    llm.py                   # GPT-4o-mini integration for screening answers
    filters.py               # title/description blacklist filtering
    logger.py                # console + CSV logging
    config.py                # config + resume YAML loading
  chrome_profile/            # persisted browser session (gitignored)
  applications.csv           # application log (gitignored)
```

## Usage

```bash
cd ~/src/Synner
python run.py               # run all 4 categories
python run.py --category SWE # run single category
python run.py --dry-run      # search and match but don't submit
python run.py --headless     # run without visible browser
```

## Phase 2 (future)

- Greenhouse portal support
- Lever portal support
- Application deduplication across sessions
- Dashboard to view application stats

# Manual QA Checklist - Synner

## Prerequisites

- [ ] Python 3.11+ installed
- [ ] Chrome browser installed
- [ ] All dependencies installed: `pip install -r requirements.txt`
- [ ] OpenAI API key available

---

## 1. Configuration Setup

- [ ] Copy `config.yaml` and fill in your OpenAI API key:
  ```yaml
  openai_api_key: "sk-your-real-key-here"
  linkedin_profile_dir: "./chrome_profile"
  resume_dir: "~/Documents/resumes/pdfs"
  max_applications_per_session: 100
  max_per_category: 30
  delay_min_seconds: 30
  delay_max_seconds: 60
  search_delay_min_seconds: 120
  search_delay_max_seconds: 300
  headless: false
  ```
- [ ] Verify `plain_text_resume.yaml` exists and contains all required sections (personal, education, experience, projects, skills, years_of_experience)
- [ ] Verify resume PDFs exist at `~/Documents/resumes/pdfs/` for all 4 categories (Resume_SWE.pdf, Resume_FS.pdf, Resume_MLAI.pdf, Resume_DE.pdf)

---

## 2. First-Run Login (Manual LinkedIn Login)

- [ ] Run: `python run.py --category SWE`
- [ ] Chrome opens with a new profile (or existing profile from `./chrome_profile`)
- [ ] Manually log into LinkedIn when prompted
- [ ] Verify the bot waits for login to complete before proceeding
- [ ] Close the bot (Ctrl+C) after login succeeds
- [ ] Re-run: `python run.py --category SWE` and verify login is persisted (no manual login needed)

---

## 3. Dry-Run Test

- [ ] Run: `python run.py --dry-run --category SWE`
- [ ] Verify the bot searches LinkedIn for SWE keywords
- [ ] Verify search results appear in the console log
- [ ] Verify title filters work: senior/staff/lead/etc. titles are SKIPPED with reason logged
- [ ] Verify description filters work: jobs requiring 5+ years are SKIPPED
- [ ] Verify clean titles (Junior, Intern, Associate, etc.) are NOT skipped
- [ ] Verify Easy Apply button detection: bot identifies which jobs have Easy Apply
- [ ] Verify NO applications are actually submitted (dry-run mode)
- [ ] Verify console output follows format: `[YYYY-MM-DD HH:MM:SS] [SWE]  STATUS  Title @ Company (Location)`

---

## 4. Easy Apply Form Detection

- [ ] Run a dry-run and observe form detection logs
- [ ] Verify the bot correctly identifies Easy Apply forms
- [ ] Verify non-Easy Apply jobs are skipped or ignored
- [ ] Verify multi-page forms are detected (if applicable)

---

## 5. Resume Upload Verification

- [ ] Run with a single category (non-dry-run, limit to 1 application if possible)
- [ ] Verify the correct resume PDF is selected for the category:
  - SWE -> Resume_SWE.pdf
  - FS -> Resume_FS.pdf
  - MLAI -> Resume_MLAI.pdf
  - DE -> Resume_DE.pdf
- [ ] Verify resume file upload field is filled correctly
- [ ] Verify no upload errors in the console

---

## 6. Screening Question Verification

- [ ] During a form fill, observe screening question answers in console/debug log
- [ ] Verify hardcoded answers are used when patterns match:
  - "Authorized to work" -> Yes
  - "Sponsorship" -> No
  - "Years of experience with [tech]" -> correct number from resume
  - "Willing to relocate" -> Yes, within DFW
  - "Salary" -> Open to discussion / competitive
  - "How did you hear" -> LinkedIn
  - "Education level" -> Bachelor's (in progress)
  - "GPA" -> 3.7
- [ ] Verify LLM-generated answers for non-hardcoded questions are reasonable
- [ ] Verify multiple-choice questions select the correct option

---

## 7. Full Run Test (Single Category)

- [ ] Run: `python run.py --category SWE`
- [ ] Monitor console output for APPLIED/SKIPPED/FAILED statuses
- [ ] Verify rate limiting: 30-60 second delays between applications
- [ ] Verify the bot stops after hitting max_per_category (30) or running out of jobs
- [ ] Verify `applications.csv` is created/updated with correct columns:
  date, category, company, title, location, status, reason, linkedin_url
- [ ] Verify end-of-session summary is printed with correct counts
- [ ] Verify token usage/cost is reported

---

## 8. CSV Log Verification

- [ ] Open `applications.csv` after a run
- [ ] Verify header row: date, category, company, title, location, status, reason, linkedin_url
- [ ] Verify each row has all 8 columns populated (reason may be empty for APPLIED)
- [ ] Verify dates are in YYYY-MM-DD HH:MM:SS format
- [ ] Verify LinkedIn URLs are valid job URLs
- [ ] Run a second session and verify rows are appended (not overwritten)

---

## 9. Dashboard Test

- [ ] Launch the dashboard (check applier/dashboard/app.py for run instructions)
- [ ] Verify the dashboard loads in a web browser
- [ ] Verify application stats are displayed correctly
- [ ] Verify history view shows logged applications
- [ ] Verify settings page displays current configuration
- [ ] Verify controls page functions as expected

---

## 10. Edge Cases

- [ ] Test with `--headless` flag: `python run.py --headless --dry-run --category SWE`
- [ ] Test with all 4 categories: `python run.py --dry-run` (no --category flag)
- [ ] Test behavior when LinkedIn session expires (delete chrome_profile and re-run)
- [ ] Test behavior with no internet connection (should fail gracefully)
- [ ] Test behavior when OpenAI API key is invalid (should report error clearly)

---

## Sign-Off

| Tester | Date | Result | Notes |
|--------|------|--------|-------|
|        |      |        |       |

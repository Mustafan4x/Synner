"""Shared fixtures for Synner test suite."""

import pytest


@pytest.fixture
def sample_config() -> dict:
    """Return a valid configuration dictionary matching config.yaml schema."""
    return {
        "openai_api_key": "sk-test-key-1234567890",
        "linkedin_profile_dir": "./chrome_profile",
        "resume_dir": "~/Documents/resumes/pdfs",
        "max_applications_per_session": 100,
        "max_per_category": 30,
        "delay_min_seconds": 30,
        "delay_max_seconds": 60,
        "search_delay_min_seconds": 120,
        "search_delay_max_seconds": 300,
        "headless": False,
    }


@pytest.fixture
def sample_resume() -> dict:
    """Return a valid resume dictionary matching plain_text_resume.yaml schema."""
    return {
        "personal": {
            "name": "Test User",
            "email": "testuser@example.com",
            "phone": "555-555-0100",
            "location": "Arlington, TX",
            "linkedin": "linkedin.com/in/test-user",
            "github": "github.com/test-user",
        },
        "education": {
            "school": "University of Texas at Arlington",
            "degree": "Bachelor of Science in Computer Science",
            "graduation": "May 2027",
            "coursework": [
                "Data Structures and Algorithms",
                "Object-Oriented Programming",
                "Software Engineering",
            ],
        },
        "experience": [
            {
                "title": "Software Engineering Intern",
                "company": "Fielder Postal Center",
                "location": "Arlington, TX",
                "dates": "May 2025 - Aug 2025",
                "bullets": [
                    "Developed internal inventory tracking scripts in Python",
                ],
            }
        ],
        "projects": [
            {
                "name": "AdrenalineAI",
                "tech": "Python, Streamlit, XGBoost, BeautifulSoup, Pandas",
                "bullets": [
                    "ML-powered UFC fight prediction platform deployed to Streamlit Community Cloud",
                    "Trained XGBoost classifier achieving 81% cross-validation accuracy",
                ],
            },
            {
                "name": "SpotMe",
                "tech": "TypeScript, React Native, Expo, SQLite, Zustand",
                "bullets": [
                    "Cross-platform fitness tracking mobile app with file-based routing",
                    "Normalized 8-table database schema with WAL mode",
                ],
            },
        ],
        "skills": {
            "languages": ["Python", "TypeScript", "JavaScript", "C/C++", "SQL"],
            "frameworks": ["React Native", "Expo", "Streamlit", "Node.js"],
            "tools": ["Git", "GitHub", "Linux", "SQLite", "PostgreSQL", "Docker"],
        },
        "years_of_experience": {
            "Python": 2,
            "TypeScript": 2,
            "JavaScript": 2,
            "SQL": 2,
            "C/C++": 2,
            "React Native": 1,
            "Git": 2,
            "Linux": 2,
            "Docker": 1,
        },
    }

# Release v1.0.0: Production-Ready AI Job Discovery Agent

**Tag:** `v1.0.0`  
**Commit:** `d52f953`  
**Date:** October 25, 2026  

---

## Highlights

The **v1.0.0** release establishes the complete, production-ready implementation of the self-hosted AI Job Fetching Agent. Designed for automated job hunting, the service ingests a candidate CV, scrapes fresh postings daily from LinkedIn via JobSpy, screens postings with low-cost language and experience agents, executes comprehensive multi-criteria skills evaluations, audits high scores with a Devil's Advocate verifier on unstripped job text, and posts rich candidate-matched alerts to Discord.

### What's Included

- **CV Ingestion & Profiling**:
  - In-memory PDF parsing via PyMuPDF with zero raw PDF disk retention.
  - Automatic extraction into a strongly typed `CandidateProfile` (skills, projects, experience, target titles).
- **Multi-Stage Evaluation Pipeline**:
  - **Fast Screening**: Concurrent language and years-of-experience verification to drop non-matching roles early.
  - **Skills Rubric**: Pydantic-validated structured outputs with deterministic Python scoring (0–100 scale).
  - **Devil's Advocate Audit**: Secondary sanity audit on roles scoring $\ge 80$ using up to 12,000 characters of raw job text to catch buried dealbreakers or recruiter boilerplate mismatches.
- **Resilience & Rate-Limiting**:
  - LinkedIn rate-limit mitigation (25-job batch pagination with progressive 60s backoff retries).
  - Pre-flight DNS/network connectivity checks before paid API executions.
  - Guaranteed state recovery (`state = "idle"`, `last_run_finished`) via outer `try...finally` wrappers.
  - Automatic classification of transient errors (`STATUS_ERROR_TRANSIENT`) for retry on subsequent runs.
- **Storage & Deduplication**:
  - Persistent SQLite database tracking job IDs, company/title fuzzy fingerprints, match scores, and status tags (`evaluated`, `filtered_lang`, `filtered_exp`, `filtered_bot`).
- **Security & Authorization**:
  - Optional `API_SECRET_KEY` authorization enforced via FastAPI dependencies for sensitive endpoints (`/profile`, `/upload-cv`, `/trigger-pipeline`).
  - Clear documentation of Cloudflare Tunnel network ingress vs. Cloudflare Access authorization policies.
  - Ephemeral in-memory handling for CV bytes.
- **CI/CD & Testing**:
  - 31 passing offline unit tests running without live API credentials or secrets.
  - GitHub Actions CI matrix running on Python 3.11 (`ci.yml`).
  - Automated deployment workflow with health-check verification (`deploy.yml`).

---

## Quickstart

```bash
# Clone and enter the repository
git clone https://github.com/ducchuu/agent-jobfetching.git
cd agent-jobfetching

# Configure environment variables
cp .env.example .env
# Edit .env with your OPENAI_API_KEY, ANTHROPIC_API_KEY, and DISCORD_WEBHOOK_URL

# Start service via Docker Compose
docker compose up -d --build

# Upload your CV (PDF)
curl --fail-with-body -X POST http://127.0.0.1:8000/upload-cv -F 'file=@/path/to/cv.pdf'

# Trigger the evaluation pipeline
curl --fail-with-body -X POST http://127.0.0.1:8000/trigger-pipeline
```

---

## Verification & Test Results

- **Unit Test Suite**: 31 passed, 3 live integration tests deselected (`pytest`).
- **Python Compatibility**: Python 3.11 (deployment target) / Python 3.12 (development).
- **CI Status**: Passing on GitHub Actions.

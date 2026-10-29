# Release v1.1.0: Multi-Location Discovery & Pipeline Control

**Tag:** `v1.1.0`  
**Date:** October 29, 2026  

---

## Highlights

The **v1.1.0** release significantly expands the search reach and performance of the AI Job Fetching Agent. It introduces multi-location round-robin scraping across targeted Dutch regions, persistent daily pagination tracking up to LinkedIn's 1,000-result cap, zero-cost multi-lingual internship filtering, and new control endpoints.

### What's New

- **Multi-Location Round-Robin Scraping**:
  - Automatically queries across configured target locations (`LOCATIONS`, default: Netherlands, Amsterdam, Utrecht, Rotterdam, Delft, Leiden).
  - Robust location parsing supporting comma-separated lists, JSON arrays, and `.env.example` empty-string defaults.
  - Automatic country resolution for Indeed (`resolve_country_indeed`) ensuring correct country domains per city.
  - Freshness window set to 72 hours for high-relevance job discovery.

- **LinkedIn 1,000-Result Daily Capping & Persistence**:
  - `location_scrape_tracking` SQLite table tracks `results_fetched`, `last_offset`, and `is_exhausted` per location and date.
  - Hard-stops pagination at `MAX_RESULTS_PER_LOCATION=1000` per location to respect LinkedIn's strict search query limit without wasted retries.
  - Seamless resume across pipeline runs on the same calendar day.

- **Zero-Cost Regex Internship Filtering**:
  - Screens out internships, traineeships, and student positions in English, Dutch, and Spanish before invoking LLMs.
  - Context-aware exclusions protect against false positives (e.g., "early-stage startup").
  - Auto-rejections recorded as `FILTERED_INTERN` in SQLite.

- **Pipeline Controls & Endpoints**:
  - `POST /stop-pipeline`: Safely halts active scraping/evaluation cycles between batches.
  - `GET /location-stats`: Returns configured search targets and per-location scraping progress for the day.
  - Both endpoints are protected by `API_SECRET_KEY` when configured.

- **Throughput & Evaluation Optimizations**:
  - Evaluation batch size increased to 10 (`EVAL_BATCH_SIZE=10`).
  - Scrape delay between location cycles reduced to 5s.
  - Immediate loop exit on stop signals without trailing sleep delays.

- **Bug Fixes & Hardening**:
  - Resolved `pydantic-settings` `SettingsError` crash when loading `.env.example` or comma-separated location strings.
  - Fixed status classification logic in `app/main.py` to prevent substrings (such as "internal" or "experience") from misclassifying skills agent rejections.
  - Hardened `clear_db.py` to gracefully handle legacy databases missing the tracking table.

- **Testing**:
  - 48 passing unit tests (up from 31 in v1.0.0), with 3 live integration tests deselected.


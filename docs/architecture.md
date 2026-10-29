# Architecture, Scoring, and Reliability

[Back to README](../README.md)

## Current scope

The release is a single-profile, single-process personal assistant. It is not a multi-user recruiting service. Multiple workers or replicas require coordination that the current design does not provide.

## Components

| Component | Responsibility |
|---|---|
| `app/main.py` | API endpoints, scheduling, pipeline execution, and live status |
| `app/agent/matcher.py` | LangGraph workflow and audit |
| `app/agent/skills_agent.py` | Structured rubric extraction |
| `app/agent/llm_router.py` | Model routes, fallbacks, tracing, and cache metrics |
| `app/models/schemas.py` | Validation, normalization, and scoring |
| `app/core/database.py` | Processing records and duplicate checks |
| `app/services/` | Scraping, CV parsing, and notifications |

Model aliases and provider IDs live in the router. Verify availability for your provider accounts; do not treat an alias as evidence of provider support.

## Evaluation path

1. Parse CV text through a provider model and cache a validated candidate profile.
2. Fetch postings through JobSpy.
3. Reject selected short descriptions containing anti-bot indicators.
4. Run language and experience checks concurrently; await both before deciding whether to continue.
5. Extract a Pydantic skills rubric.
6. Calculate an initial score in Python.
7. For scores reaching `MATCH_THRESHOLD`, perform a best-effort audit.
8. Suppress rejected/below-threshold results; notify eligible matches and record processing outcomes.

The auditor receives `raw_description` when present, otherwise `description`. Scraping caps these at 12,000 and 8,000 characters respectively. Neither is guaranteed to include the entire original posting.

## Scoring formula

```text
initial_score = clamp(85 + B - 10*C - 3*S, 0, 100)
```

- `B`: model-selected project-relevance bonus, 0–15.
- `C`: count of missing core skills.
- `S`: count of missing secondary skills.
- A hard dealbreaker produces zero.

The schema removes case/whitespace duplicates in missing-skill lists and avoids penalizing an identical skill as both core and secondary. Semantic synonyms can still be counted separately.

The base score is 85. Matched skills do not independently add points. Empty missing-skill lists and no bonus therefore produce 85; those lists default to empty when omitted. Extraction completeness is important.

Arithmetic is deterministic for a given rubric; extraction, bonuses, and audit judgments remain model-dependent. Weights are manually selected heuristics, not empirically calibrated hiring probabilities.

## Audit policy

The audit checks unsupported skill claims and non-technical dealbreakers. A validated hard-dealbreaker response rejects the match. A critical-flaw response subtracts up to 15 points; the reviewed implementation uses a 10-point fallback when that flag is true but the penalty is zero.

Audit call/validation failures retain the original result, which can still generate an alert. This is a best-effort policy, not mandatory successful verification.

Mocked audit tests establish prompt contents and response handling. They do not establish live-model accuracy. The retained raw-description path helps expose trimmed requirements only for postings reaching the audit stage.

## Concurrency and limits

- Up to 10 postings are evaluated concurrently in batches (`EVAL_BATCH_SIZE=10`).
- Each posting runs two eligibility (experience and language) checks concurrently, preceded by a zero-cost regex screening for internships and anti-bot markers.
- Postings are fetched in batches of 25 across configured locations (`LOCATIONS`, e.g., Netherlands, Spain, Amsterdam, Barcelona, etc.).
- Daily pagination per location is capped at 1,000 results (`MAX_RESULTS_PER_LOCATION=1000`) to respect upstream LinkedIn limits, tracked persistently in SQLite (`location_scrape_tracking`).
- Completed skills evaluations can be capped with `TARGET_SKILLS_EVALUATIONS` (defaults to unbounded, scanning all active locations until exhausted or limit reached).
- Active pipeline executions can be paused/cancelled via `POST /stop-pipeline`.
- The scheduler requests a run at 07:00 Europe/Amsterdam while active.

The lock, scheduler, and live status are process-local. Background tasks are not a durable queue, and interrupted work is not guaranteed to resume after restart.

## Persistence and retries

Statuses include `FILTERED_BOT`, `FILTERED_INTERN`, `FILTERED_LANG`, `FILTERED_EXP`, `EVALUATED`, and `ERROR_TRANSIENT`.

Malformed skills JSON and rubric validation failures are treated as retryable evaluation errors. An `ERROR_TRANSIENT` record makes a rediscovered posting eligible again; it does not itself schedule a retry.

Source IDs and normalized company/title fingerprints provide heuristic deduplication. Same-title vacancies at one company may be merged across locations or teams. Check/record operations do not establish exactly-once processing, especially under concurrency.

Notification delivery and processing records are not a transactional outbox. Do not assume exactly-once alerts or automatic recovery of every delivery failure.

## Optimizations and limitations

- Early filters avoid some expensive calls but can introduce false negatives.
- A stable profile/example prefix supports provider-dependent prompt caching. Eligibility does not guarantee cache hits or a fixed discount; inspect logged usage.
- Trailing boilerplate slicing applies only after the 55% position. Unexpected layouts can remove useful content.
- The current pipeline passes `target_yoe=0`. Review this policy before using an experienced candidate's CV.

Use tests and recorded runs to support performance/cost claims. The architecture alone does not establish accuracy or percentage savings.

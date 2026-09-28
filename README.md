# AI Job Fetching Agent

An automated pipeline designed to scrape, evaluate, and fetch job listings tailored to specific criteria. This project uses web scraping and an AI agent to match job descriptions against user-defined preferences.

- **Job Scraping**: Automatically fetches job listings (e.g., AI Engineer, Robotics Engineer) in specified locations.
- **AI-Powered Evaluation**: Analyzes job descriptions using AI to determine how well they match desired skills and requirements.
- **Dockerized API**: Fully containerized FastAPI backend.
- **Cloudflare Tunnels**: Ready to be securely exposed to the web using Cloudflare Tunnels.

## Project Structure

```text
agent_jobfetching/
├── app/                  # Main application package
│   ├── agent/            # AI agent logic for evaluating jobs
│   ├── core/             # Core utilities and settings
│   ├── models/           # Data models (Pydantic/SQLAlchemy)
│   ├── services/         # Business logic (e.g., scraper integration)
│   └── main.py           # Application entrypoint (FastAPI)
├── data/                 # Directory containing the SQLite database (jobs.db)
├── tests/                # Unit and integration tests
├── .env.example          # Example environment variables
├── docker-compose.yml    # Docker setup for local server & Cloudflare tunnel
├── Dockerfile            # Docker instructions for building the API
├── pyproject.toml        # Project configuration
├── requirements.txt      # Python dependencies
├── run_job_scraper.py    # Utility script to test scraping
└── clear_db.py           # Utility script to reset the database
```

## Utility Scripts

You will notice a couple of standalone `.py` scripts at the root level, like run_job_scraper.py and clear_db.py. These are used for testing and database management outside the main API loop, useful for anyone running the pipeline.

### `run_job_scraper.py`
This script allows you to independently test the job scraping service without running the full AI evaluation pipeline. It fetches jobs for predefined titles (like "AI Engineer", "Robotics Engineer") in a specific location (e.g., "Netherlands") and prints the results directly to your console. 
- **Why it's useful:** It's great for debugging scraper issues, verifying API keys, and quickly checking what job data is currently available on the market.

### `clear_db.py`
The agent uses a local SQLite database (`data/jobs.db`) to keep track of which jobs have already been evaluated, ensuring it doesn't process the same job twice. Running this script deletes all records from the `processed_jobs` table.
- **Why it's useful:** If you want to reset the pipeline state (for example, if you tweaked the AI agent's prompt and want it to re-evaluate jobs it previously skipped), running this script will make the pipeline treat all found jobs as brand new.

## Guidance to run

### 1. Personalize
The project is based on the prompt engineering through the pipeline, therefore the prompts have to be adjusted to match the candidates needs. In my case, I do not have any work experience, as a job, therefore I specify how to handle this and describe instructions on how to calculate the match score.

Hence you should update:

`app/services/cv_parser.py`

and

`app/agent/matcher.py`


### 2. Deployment
The project includes a `docker-compose.yml` configured to run the API and optionally expose it via a Cloudflare Tunnel.

1. **Set up `.env`:** Ensure your `.env` file is fully configured, including your `CLOUDFLARE_TUNNEL_TOKEN`.
2. **Build and Run:**
   ```bash
   docker-compose up -d --build
   ```
3. **Check Logs:**
   ```bash
   docker-compose logs -f api
   ```
4. **Shutdown:**
   ```bash
   docker-compose down
   ```


### 3. Local Development (Without Docker)
1. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment:**
   Copy `.env.example` to `.env` and fill in your API keys (e.g., OpenAI API key, SerpApi key).
4. **Run the API:**
   ```bash
   uvicorn app.main:app --reload
   ```

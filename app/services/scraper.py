from jobspy import scrape_jobs
from app.models.schemas import JobPosting
from app.core.database import compute_fingerprint
import logging
import re
import socket
from typing import Optional

logger = logging.getLogger(__name__)

COUNTRY_CITY_MAP = {
    # Netherlands
    "netherlands": "Netherlands",
    "nederland": "Netherlands",
    "amsterdam": "Netherlands",
    "utrecht": "Netherlands",
    "rotterdam": "Netherlands",
    "delft": "Netherlands",
    "eindhoven": "Netherlands",
    "the hague": "Netherlands",
    "den haag": "Netherlands",
    "groningen": "Netherlands",
    "leiden": "Netherlands",
}

def resolve_country_indeed(location: str) -> str:
    loc_clean = location.strip().lower()
    if loc_clean in COUNTRY_CITY_MAP:
        return COUNTRY_CITY_MAP[loc_clean]
    for key, country in COUNTRY_CITY_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", loc_clean):
            return country
    return location

class NetworkError(Exception):
    # for raising error when a DNS or TCP connectivity failure 
    pass

def fetch_daily_jobs(
    target_job_titles: list[str], 
    location: str = "Netherlands",
    job_type: str = "fulltime", # here can be "fulltime", "internship", "parttime"
    results_wanted: int = 25,
    offset: int = 0,
    country_indeed: Optional[str] = None
) -> list[JobPosting]:
    
    logger.info(f"Scraping jobs for dynamic titles: {target_job_titles} (offset: {offset})")
    
    search_query = " OR ".join([f'"{title}"' for title in target_job_titles])
    effective_country_indeed = country_indeed or resolve_country_indeed(location)
    
    try:
        # scrape across only LinkedIn and Indeed, because JobSpy API doesn't support magnet.me 
        jobs_df = scrape_jobs(
            site_name=["linkedin", "indeed"],
            search_term=search_query,
            location=location,
            job_type=job_type,
            results_wanted=results_wanted,
            offset=offset,
            hours_old=72, # only jobs posted in the last 3 days
            country_indeed=effective_country_indeed,
            linkedin_fetch_description=True # this is an jobspy api restriction that forces LinkedIn to fetch descriptions to avoid nan
        )
    except Exception as e:
        err_str = str(e)
        # NameResolutionError / socket.gaierror both indicate DNS failure
        if "NameResolutionError" in err_str or "Failed to resolve" in err_str or isinstance(e, socket.gaierror):
            raise NetworkError(f"DNS/network failure during scrape: {e}") from e
        logger.error(f"Scraper error during scrape_jobs (offset {offset}): {e}")
        return []
    
    import pandas as pd
    
    if jobs_df is None or jobs_df.empty:
        logger.info(f"JobSpy returned 0 raw jobs for query at offset {offset}.")
        return []

    # eliminate duplicates based on job title and company
    jobs_df = jobs_df.drop_duplicates(subset=['title', 'company'])
    
    seen_fingerprints = set()
    job_postings = []
    for _, row in jobs_df.iterrows():
        # ensure we have the minimum viable data
        if pd.isna(row.get('description')) or not str(row.get('description')).strip() or str(row.get('description')).lower() == 'nan':
            continue
            
        title_str = str(row['title'])
        company_str = str(row.get('company', 'Unknown'))
        fp = compute_fingerprint(company_str, title_str)
        if fp and fp in seen_fingerprints:
            continue
        if fp:
            seen_fingerprints.add(fp)

        raw_desc = str(row['description'])
        
        # Token optimization: Strip only trailing HR boilerplate if it occurs in the bottom half of the JD
        trailing_boilerplate = [
            r"(?i)\b(benefits\s*(&|and)?\s*perks)\b",
            r"(?i)\b(what we offer)\b",
            r"(?i)\b(equal opportunity employer)\b",
            r"(?i)\b(diversity and inclusion)\b",
            r"(?i)\b(our culture)\b",
            r"(?i)\b(why join us)\b"
        ]
        
        cleaned_desc = raw_desc
        min_cutoff_pos = int(len(cleaned_desc) * 0.55)
        for pattern in trailing_boilerplate:
            match = re.search(pattern, cleaned_desc)
            if match and match.start() >= min_cutoff_pos:
                cleaned_desc = cleaned_desc[:match.start()].strip()
                break
                
        # fallback in case it fails, takes back all 8000 tokens
        cleaned_desc = cleaned_desc[:8000]

        job_postings.append(JobPosting(
            id=str(row['id']),
            title=str(row['title']),
            company=str(row.get('company', 'Unknown')),
            description=cleaned_desc,
            raw_description=raw_desc[:12000],
            url=str(row.get('job_url', '')),
            location=str(row.get('location', location) or location)
        ))
        
    logger.info(f"JobSpy fetched {len(jobs_df)} raw jobs. Processed into {len(job_postings)} valid postings with descriptions.")
    return job_postings

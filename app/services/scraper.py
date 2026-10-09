from jobspy import scrape_jobs
from app.models.schemas import JobPosting
import logging
import re

logger = logging.getLogger(__name__)

def fetch_daily_jobs(
    target_job_titles: list[str], 
    location: str = "Netherlands",
    job_type: str = "fulltime", # here can be "fulltime", "internship", "parttime"
    results_wanted: int = 200,
    offset: int = 0
) -> list[JobPosting]:
    
    logger.info(f"Scraping jobs for dynamic titles: {target_job_titles} (offset: {offset})")
    
    search_query = " OR ".join([f'"{title}"' for title in target_job_titles])
    
    # scrape across only LinkedIn and Indeed, because JobSpy API doesn't support magnet.me 
    jobs_df = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term=search_query,
        location=location,
        results_wanted=results_wanted,
        offset=offset,
        hours_old=72, # only jobs posted in the last 3 days
        country_indeed='Netherlands',
        linkedin_fetch_description=True # this is an jobspy api restriction that forces LinkedIn to fetch descriptions to avoid nan
    )
    
    import pandas as pd
    
    # eliminate duplicates based on job title and company
    if not jobs_df.empty:
        jobs_df = jobs_df.drop_duplicates(subset=['title', 'company'])
    
    job_postings = []
    for _, row in jobs_df.iterrows():
        # ensure we have the minimum viable data
        if pd.isna(row.get('description')) or not str(row.get('description')).strip() or str(row.get('description')).lower() == 'nan':
            continue
            
        raw_desc = str(row['description'])
        
        # 1st token optimization technique of stripping all unneccessary content from the fetched jobs, that doesn't really match the skills agent purpose
        boilerplate_patterns = [
            r"(?i)\b(about the company)\b",
            r"(?i)\b(benefits & perks)\b",
            r"(?i)\b(what we offer)\b",
            r"(?i)\b(equal opportunity employer)\b",
            r"(?i)\b(diversity and inclusion)\b",
            r"(?i)\b(our culture)\b",
            r"(?i)\b(why join us)\b"
        ]
        
        cleaned_desc = raw_desc
        for pattern in boilerplate_patterns:
            match = re.search(pattern, cleaned_desc)
            if match:
                cleaned_desc = cleaned_desc[:match.start()].strip()
                break
                
        # fallback in case it fails, takes back all 8000 tokens
        cleaned_desc = cleaned_desc[:8000]

        job_postings.append(JobPosting(
            id=str(row['id']),
            title=str(row['title']),
            company=str(row.get('company', 'Unknown')),
            description=cleaned_desc,
            url=str(row.get('job_url', ''))
        ))
        
    return job_postings

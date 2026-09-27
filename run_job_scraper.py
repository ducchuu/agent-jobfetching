from app.services.scraper import fetch_daily_jobs

def main():
    print("Testing the job scraper...")
    
    # We will test fetching just a couple of targeted roles
    target_titles = ["AI Engineer", "Robotics Engineer"]
    
    print(f"Target Titles: {target_titles}")
    print("Location: Netherlands")
    print("Fetching jobs... this might take 10-20 seconds...\n")
    
    try:
        jobs = fetch_daily_jobs(
            target_job_titles=target_titles, 
            location="Netherlands", 
            job_type="fulltime"
        )
        
        print(f"\n--- SUCCESS! Found {len(jobs)} jobs ---\n")
        
        for i, job in enumerate(jobs):
            print(f"Job #{i+1}:")
            print(f"  Title:   {job.title}")
            print(f"  Company: {job.company}")
            print(f"  URL:     {job.url}")
            print(f"  Desc Snippet: {job.description[:100]}...\n")
            
    except Exception as e:
        print(f"An error occurred while scraping: {e}")

if __name__ == "__main__":
    main()

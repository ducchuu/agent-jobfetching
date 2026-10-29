import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "data/jobs.db")

def main():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} does not exist yet. Nothing to clear.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # count rows before deleting 
        cursor.execute("SELECT COUNT(*) FROM processed_jobs")
        count = cursor.fetchone()[0]
        
        cursor.execute("DELETE FROM processed_jobs")
        try:
            cursor.execute("DELETE FROM location_scrape_tracking")
        except sqlite3.OperationalError:
            pass  # Table might not exist yet on legacy schema
        conn.commit()
        
        print(f"Successfully cleared {count} jobs and daily location tracking from the database!")
        print("The pipeline will now analyze all jobs again as if they were brand new.")
        
    except sqlite3.OperationalError as e:
        print(f"Error accessing database (it might be locked or uninitialized): {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()

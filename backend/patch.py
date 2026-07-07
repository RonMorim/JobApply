import sqlite3

conn = sqlite3.connect('jobs.db')
cursor = conn.cursor()

# 1. ניקוי מוחלט של מפתחות החסימה ההיסטוריים
keys = ['linkedin_scraper_status', 'linkedin_redirect_error_count', 'linkedin_scraper_blocked_at', 'linkedin_cookie_status', 'linkedin_scraper_paused']
for k in keys:
    try: cursor.execute("DELETE FROM kv_store WHERE key = ?", (k,))
    except: pass
    try: cursor.execute("DELETE FROM kv_store WHERE k = ?", (k,))
    except: pass

# 2. הכנת תיאור המשרה המלא של Mint
mint_jd = """Company Description Mint is an Israeli digital agency building B2C websites and apps for the country's leading brands — Bank Hapoalim, Ashtrom, Delek Motors, Histadrut, and more. Overview Looking for a rockstar Project Manager — early in their product journey About the Role Lead digital projects end-to-end — from the first client brief through launch Serve as the main professional point of contact for clients: managing expectations, running status meetings, documenting decisions Write PRDs, specs, and user stories at a level that lets development run without getting stuck Work closely with development, design, and QA teams — translating client needs into clear work plans Identify product opportunities and manage scope changes in a structured way Qualifications What We're Looking For — Experience 1–3 years of experience managing digital projects (websites / apps / web systems) Proven experience working directly with clients, ideally large organizations Experience writing specs / PRDs / user stories Proficiency with project management tools (Jira / Monday / Asana) Experience working with both in-house and external development teams Experience with B2C clients What We're Looking For — Mindset A genuine love for clients — not patience, love. Real curiosity about their business Backbone: the ability to say no to clients when needed and protect the team Emerging product mindset — curiosity about the why behind user behavior, not just the what Obsessive organization — if something falls through the cracks, it'll keep you up at night Initiative and ownership — doesn't wait to be told what to do Nice to Have Experience at a digital agency or software house Familiarity with Umbraco Why Join Us Clear growth path to Product Manager within the team Exposure to a wide variety of clients, industries, and technologies A team that believes a great PM is half the success of any project — not the person who updates Jira"""

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
t = 'jobs' if 'jobs' in tables else (tables[0] if tables else None)

if t:
    cursor.execute(f"PRAGMA table_info({t})")
    cols = [row[1] for row in cursor.fetchall()]
    id_c = 'job_id' if 'job_id' in cols else 'id'
    d_c = 'description' if 'description' in cols else ('job_description' if 'job_description' in cols else 'raw_text')
    
    cursor.execute(f"SELECT {id_c} FROM {t} WHERE title LIKE '%Mint%'")
    res = cursor.fetchone()
    if res:
        cursor.execute(f"UPDATE {t} SET {d_c}=?, score_is_proxy=0, enrichment_failures=0 WHERE {id_c}=?", (mint_jd, res[0]))
        print(f"Successfully patched Mint (Job ID: {res[0]}) and cleared block state.")
    else:
        print("Mint job record not found in database.")
else:
    print("No tables found.")

conn.commit()
conn.close()
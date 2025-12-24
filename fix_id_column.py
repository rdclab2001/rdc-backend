import sqlite3

conn = sqlite3.connect("rdc.db")
cur = conn.cursor()

# 1. Create new table with id
cur.execute("""
CREATE TABLE IF NOT EXISTS website_leads_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    mobile TEXT,
    test_type TEXT,
    message TEXT,
    address TEXT,
    status TEXT DEFAULT 'pending'
)
""")

# 2. Copy data from old table
cur.execute("""
INSERT INTO website_leads_new (name, mobile, test_type, message, address, status)
SELECT name, mobile, test_type, message, address, status FROM website_leads
""")

# 3. Drop old table
cur.execute("DROP TABLE website_leads")

# 4. Rename new table
cur.execute("ALTER TABLE website_leads_new RENAME TO website_leads")

conn.commit()
conn.close()

print("id column added successfully!")

import sqlite3

conn = sqlite3.connect("rdc.db")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE bookings ADD COLUMN seen INTEGER DEFAULT 0")
    print("✅ 'seen' column added successfully")
except sqlite3.OperationalError as e:
    print("⚠️ Column already exists or error:", e)

conn.commit()
conn.close()

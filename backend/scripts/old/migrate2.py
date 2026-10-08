import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'finops_v4.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE tickets ADD COLUMN assigned_to_name TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN assigned_by_name TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN assigned_at TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN completed_by_name TEXT")
    cursor.execute("ALTER TABLE tickets ADD COLUMN completed_at TEXT")
    conn.commit()
    print("Audit columns added.")
except sqlite3.OperationalError as e:
    print(f"Error (columns might already exist): {e}")
conn.close()

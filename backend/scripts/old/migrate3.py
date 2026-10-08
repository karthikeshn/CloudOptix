import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'finops_v4.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE tickets ADD COLUMN recommended_action TEXT")
    conn.commit()
    print("recommended_action column added.")
except sqlite3.OperationalError as e:
    print(f"Error (column might already exist): {e}")
conn.close()

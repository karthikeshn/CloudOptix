import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'finops_v4.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("UPDATE tickets SET recommended_action = 'Delete Resource' WHERE recommended_action IS NULL")
conn.commit()
conn.close()
print("Backfilled recommended_action")

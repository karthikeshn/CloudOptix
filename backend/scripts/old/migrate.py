import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'finops_v4.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE cloud_configs ADD COLUMN aws_account_id VARCHAR")
except Exception as e:
    print(e)
cursor.execute("UPDATE cloud_configs SET aws_account_id = '123456789012' WHERE aws_account_id IS NULL")
conn.commit()
conn.close()
print("Migration completed")

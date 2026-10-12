import sqlite3

conn = sqlite3.connect(r'd:\FinOpsDashboard\backend\data\test_finops.db')
c = conn.cursor()

# 1. Ensure account 3 is named 'Moto Mock Sandbox' and assigned to user 1
c.execute("UPDATE cloud_configs SET owner_id = 1, account_name = 'Moto Mock Sandbox' WHERE id = 3")

# 2. Move Moto-generated tickets (121, 122, 123, 124) strictly into account 3
c.execute("UPDATE tickets SET account_id = 3 WHERE id IN (121, 122, 123, 124)")

conn.commit()
print("Successfully isolated mock tickets to 'Moto Mock Sandbox' (Account ID 3)!")

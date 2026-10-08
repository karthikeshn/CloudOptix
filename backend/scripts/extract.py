import gzip
import shutil
import os

gz_path = r'd:\FinOpsDashboard\backend\data\FinOpstestkarthik-00001.csv.gz'
csv_path = r'd:\FinOpsDashboard\backend\data\FinOpstestkarthik-00001.csv'

try:
    with gzip.open(gz_path, 'rb') as f_in:
        with open(csv_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    print(f"Successfully extracted to {csv_path}")
except Exception as e:
    print(f"Error: {e}")

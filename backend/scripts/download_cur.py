import sqlite3
import os
import boto3
import sys

def main():
    conn = sqlite3.connect('d:/FinOpsDashboard/backend/data/finops_v4.db')
    cursor = conn.cursor()
    cursor.execute('SELECT aws_access_key_id, aws_secret_access_key, aws_session_token, region FROM cloud_configs WHERE aws_access_key_id IS NOT NULL LIMIT 1')
    row = cursor.fetchone()

    if not row:
        print('No AWS credentials found in database.')
        sys.exit(1)

    access_key, secret_key, session_token, region = row

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        region_name=region or 'us-east-1'
    )

    s3 = session.client('s3')
    try:
        buckets = s3.list_buckets()['Buckets']
        print(f'Found {len(buckets)} buckets.')
        
        cur_bucket = None
        for b in buckets:
            try:
                objs = s3.list_objects_v2(Bucket=b['Name'], Prefix='mys3pathcurreport/', MaxKeys=1)
                if 'Contents' in objs:
                    cur_bucket = b['Name']
                    print(f'Found CUR folder in bucket: {cur_bucket}')
                    break
            except Exception as e:
                pass
                
        if cur_bucket:
            print(f'\\nListing contents of {cur_bucket}/mys3pathcurreport/:')
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=cur_bucket, Prefix='mys3pathcurreport/'):
                for obj in page.get('Contents', []):
                    print(f' - {obj["Key"]} ({obj["Size"]} bytes)')
                    
                    # If we find a csv or parquet file, download it!
                    if obj["Key"].endswith('.csv.gz') or obj["Key"].endswith('.parquet') or obj["Key"].endswith('.csv'):
                        print(f"Downloading {obj['Key']}...")
                        filename = os.path.basename(obj['Key'])
                        download_path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
                        os.makedirs(os.path.dirname(download_path), exist_ok=True)
                        s3.download_file(cur_bucket, obj['Key'], download_path)
                        print(f"Saved to {download_path}")
                        
        else:
            print('Could not find mys3pathcurreport/ in any bucket.')
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    main()

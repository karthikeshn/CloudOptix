import boto3
import pandas as pd
import os
import glob
from botocore.config import Config
import gzip
import shutil

AWS_CONFIG = Config(
    retries={
        "mode": "adaptive",
        "max_attempts": 10,
    }
)

def create_clients(region_name: str):
    # CUR service is available only in us-east-1 for report definitions
    cur = boto3.client('cur', region_name='us-east-1', config=AWS_CONFIG)
    s3 = boto3.client('s3', region_name=region_name, config=AWS_CONFIG)
    sts = boto3.client('sts', config=AWS_CONFIG)
    return cur, s3, sts

def get_account_id(sts):
    return sts.get_caller_identity()["Account"]

def fetch_and_query_cur(region_name: str = "us-east-1"):
    try:
        cur, s3, sts = create_clients(region_name)
        account_id = get_account_id(sts)
        
        # 1. Describe report definitions to find the S3 bucket
        response = cur.describe_report_definitions()
        report_defs = response.get('ReportDefinitions', [])
        
        if not report_defs:
            print("No CUR report definitions found.")
            return {
                "summary": [],
                "error": "No CUR report definitions found in this account."
            }
        
        # Use the first report definition
        report = report_defs[0]
        bucket = report.get('S3Bucket')
        prefix = report.get('S3Prefix', '')
        report_name = report.get('ReportName')
        
        # 2. Find the latest CUR files in the bucket
        print(f"Searching for CUR files in bucket: {bucket}, prefix: {prefix}")
        
        # We look for files in the bucket. CUR typically delivers them to:
        # <prefix>/<report_name>/YYYYMMDD-YYYYMMDD/
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        csv_files = []
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.csv.gz') or key.endswith('.parquet'):
                    csv_files.append(obj)
                    
        if not csv_files:
            return {
                "summary": [],
                "error": "No CUR data files found in the specified S3 bucket."
            }
            
        # Sort by last modified and take the most recent partition files
        csv_files.sort(key=lambda x: x['LastModified'], reverse=True)
        latest_file = csv_files[0]
        latest_key = latest_file['Key']
        
        local_dir = "temp_cur_data"
        os.makedirs(local_dir, exist_ok=True)
        local_file_path = os.path.join(local_dir, os.path.basename(latest_key))
        
        # 3. Download the file
        print(f"Downloading {latest_key} to {local_file_path}")
        s3.download_file(bucket, latest_key, local_file_path)
        
        # 4. Process the data locally using Pandas
        print("Processing data locally...")
        df = None
        if local_file_path.endswith('.gz'):
            with gzip.open(local_file_path, 'rt') as f:
                df = pd.read_csv(f, low_memory=False)
        elif local_file_path.endswith('.csv'):
            df = pd.read_csv(local_file_path, low_memory=False)
        elif local_file_path.endswith('.parquet'):
            df = pd.read_parquet(local_file_path)
            
        if df is None or df.empty:
            return {
                "summary": [],
                "error": "Downloaded file was empty or unsupported format."
            }
            
        # Clean up columns (CUR column names can be very long e.g., lineItem/ProductCode)
        df.columns = [col.split('/')[-1] if '/' in col else col for col in df.columns]
        
        # Determine product code and cost columns
        product_col = 'ProductCode' if 'ProductCode' in df.columns else 'product_code'
        cost_col = 'UnblendedCost' if 'UnblendedCost' in df.columns else 'unblended_cost'
        desc_col = 'ItemDescription' if 'ItemDescription' in df.columns else 'item_description'
        
        if cost_col not in df.columns:
            # try finding columns that look like cost
            cost_cols = [c for c in df.columns if 'cost' in c.lower()]
            if cost_cols:
                cost_col = cost_cols[0]
            else:
                return {"summary": [], "error": "Could not find cost column in CUR data."}
                
        if product_col not in df.columns:
            product_col = df.columns[0] # fallback
            
        # Convert cost to numeric
        df[cost_col] = pd.to_numeric(df[cost_col], errors='coerce').fillna(0)
        
        # Aggregate cost by Service
        summary_df = df.groupby(product_col)[cost_col].sum().reset_index()
        summary_df = summary_df.sort_values(by=cost_col, ascending=False).head(50) # top 50
        summary_df.rename(columns={product_col: 'Service', cost_col: 'TotalCost'}, inplace=True)
        summary_df['TotalCost'] = summary_df['TotalCost'].round(2)
        
        # Convert to dictionary
        findings = []
        for _, row in summary_df.iterrows():
            findings.append({
                "accountId": account_id,
                "region": region_name,
                "Service": row['Service'],
                "TotalCost": row['TotalCost'],
                "status": "Active" if row['TotalCost'] > 0 else "Inactive",
                "workItemType": "Task",
                "title": f"CUR Cost Summary: {row['Service']}",
                "category": "AWS CUR Report",
                "areaPath": "AWS Cost Dashboard",
                "type": "Cost Breakdown",
                "effortLevel": "None",
                "message": f"Total cost for {row['Service']} is ${row['TotalCost']}"
            })
            
        # Clean up downloaded file
        shutil.rmtree(local_dir, ignore_errors=True)
        
        return {"summary": findings, "error": None}
        
    except Exception as e:
        return {"summary": [], "error": str(e)}

if __name__ == "__main__":
    result = fetch_and_query_cur()
    findings = result.get("summary", [])
    
    if findings:
        df_out = pd.DataFrame(findings)
        output_file = "output_FetchCURReportLocal.csv"
        df_out.to_csv(output_file, index=False)
        print(f"Successfully generated {output_file} with {len(findings)} records.")
    else:
        print("Failed or no data found:")
        print(result.get("error"))
        # create empty so frontend doesn't break
        df_out = pd.DataFrame(columns=["accountId", "Service", "TotalCost", "message"])
        df_out.to_csv("output_FetchCURReportLocal.csv", index=False)

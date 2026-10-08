import sys
import os
import pandas as pd
import glob

CUR_DIR = r"d:\FinOpsDashboard\Cur report"

def test():
    zip_files = glob.glob(os.path.join(CUR_DIR, "*.csv.zip"))
    df_list = []
    for file in zip_files:
        df = pd.read_csv(file, compression='zip', dtype=str)
        df_list.append(df)
        
    all_df = pd.concat(df_list, ignore_index=True)
    
    if 'product/ProductName' in all_df.columns:
        if 'lineItem/ProductCode' in all_df.columns:
            all_df['Service'] = all_df['product/ProductName'].fillna(all_df['lineItem/ProductCode'])
        else:
            all_df['Service'] = all_df['product/ProductName'].fillna('Unknown')
    else:
        all_df['Service'] = all_df['lineItem/ProductCode']
        
    print("Matches for Bedrock in Service:")
    bedrock_df = all_df[all_df['Service'].astype(str).str.contains('Bedrock', case=False, na=False)]
    if bedrock_df.empty:
        print("No Bedrock in Service!")
    else:
        print(bedrock_df[['Service', 'product/productFamily', 'lineItem/ProductCode']].drop_duplicates())

test()

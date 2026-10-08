import pandas as pd
import glob
import os
import threading
from typing import List

CUR_DIR = r"d:\FinOpsDashboard\Cur report"

_cached_df = None
_cache_lock = threading.Lock()

def get_cur_dataframe():
    global _cached_df
    with _cache_lock:
        if _cached_df is not None:
            return _cached_df

    zip_files = glob.glob(os.path.join(CUR_DIR, "*.csv.zip"))
    df_list = []
    for file in zip_files:
        df = pd.read_csv(file, compression='zip', dtype=str)
        df_list.append(df)
    if not df_list:
        _cached_df = pd.DataFrame()
        return _cached_df
    
    all_df = pd.concat(df_list, ignore_index=True)
    if 'lineItem/ProductCode' not in all_df.columns:
        if 'product_code' in all_df.columns:
            all_df['lineItem/ProductCode'] = all_df['product_code']
            
    # Create a cleaner 'Service' column using ProductName if available
    if 'product/ProductName' in all_df.columns:
        if 'lineItem/ProductCode' in all_df.columns:
            all_df['Service'] = all_df['product/ProductName'].fillna(all_df['lineItem/ProductCode'])
        else:
            all_df['Service'] = all_df['product/ProductName'].fillna('Unknown')
    else:
        if 'lineItem/ProductCode' in all_df.columns:
            all_df['Service'] = all_df['lineItem/ProductCode']
        else:
            all_df['Service'] = 'Unknown'
            
    all_df['Service'] = all_df['Service'].astype(str)
            
    _cached_df = all_df
    return _cached_df

def get_main_services():
    df = get_cur_dataframe()
    if df.empty or 'Service' not in df.columns:
        return []
    services = df['Service'].dropna().unique().tolist()
    return sorted(services)

def get_ecosystems(service_names: List[str]):
    df = get_cur_dataframe()
    if df.empty or 'Service' not in df.columns or 'product/productFamily' not in df.columns:
        return []
    if not service_names:
        return []
    filtered = df[df['Service'].isin(service_names)]
    ecosystems = filtered['product/productFamily'].dropna().unique().tolist()
    return sorted(ecosystems)

def get_resource_costs(service_names: List[str], ecosystem_names: List[str]):
    df = get_cur_dataframe()
    if df.empty:
        return []
    if not service_names or not ecosystem_names:
        return []
    
    filtered = df[(df['Service'].isin(service_names)) & (df['product/productFamily'].isin(ecosystem_names))].copy()
    
    if filtered.empty:
        return []
        
    filtered['lineItem/UnblendedCost'] = pd.to_numeric(filtered['lineItem/UnblendedCost'], errors='coerce').fillna(0)
    filtered['lineItem/UsageAmount'] = pd.to_numeric(filtered['lineItem/UsageAmount'], errors='coerce').fillna(0)
    
    filtered['lineItem/ResourceId'] = filtered['lineItem/ResourceId'].fillna('Unallocated / No ID')
    filtered.loc[filtered['lineItem/ResourceId'] == '', 'lineItem/ResourceId'] = 'Unallocated / No ID'

    grouped = filtered.groupby(['lineItem/ResourceId', 'lineItem/UsageType', 'lineItem/Operation']).agg({
        'lineItem/UnblendedCost': 'sum',
        'lineItem/UsageAmount': 'sum'
    }).reset_index()

    grouped = grouped[grouped['lineItem/UnblendedCost'] > 0]
    grouped = grouped.sort_values(by=['lineItem/UnblendedCost'], ascending=False)
    
    results = []
    for _, row in grouped.iterrows():
        results.append({
            "resource_id": row['lineItem/ResourceId'],
            "usage_type": row['lineItem/UsageType'],
            "operation": row['lineItem/Operation'],
            "cost": float(row['lineItem/UnblendedCost']),
            "usage_amount": float(row['lineItem/UsageAmount'])
        })
    return results

def get_historical_cost(resource_id, account_id=None, fallback_cost=0.0):
    df = get_cur_dataframe()
    if df.empty:
        return fallback_cost
        
    mask = df['lineItem/ResourceId'].str.contains(resource_id, na=False, case=False)
    filtered = df[mask].copy()
    
    if filtered.empty:
        return fallback_cost
        
    filtered['lineItem/UnblendedCost'] = pd.to_numeric(filtered['lineItem/UnblendedCost'], errors='coerce').fillna(0)
    total = filtered['lineItem/UnblendedCost'].sum()
    
    return float(total) if total > 0 else fallback_cost

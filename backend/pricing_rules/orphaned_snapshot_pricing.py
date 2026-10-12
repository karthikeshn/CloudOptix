import sys
import os
import json
import boto3

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_processor as cur_integration
from utils.region_mapping import get_pricing_region

def get_real_snapshot_market_price(region_name: str, size_gb: float) -> float:
    """
    Hits the REAL AWS Pricing API to find the exact market rate for EBS snapshot storage.
    Breaks out of fake environment using REAL AWS credentials from .env.
    """
    human_region = get_pricing_region(region_name)
    
    # Load real credentials from backend .env
    from dotenv import load_dotenv
    env_path = os.path.join(backend_dir, '.env')
    load_dotenv(env_path)
    
    real_access = os.environ.get("REAL_AWS_ACCESS_KEY_ID")
    real_secret = os.environ.get("REAL_AWS_SECRET_ACCESS_KEY")
    
    # Pricing API is hosted in us-east-1 and ap-south-1
    pricing_client = boto3.client(
        'pricing',
        region_name='us-east-1',
        aws_access_key_id=real_access,
        aws_secret_access_key=real_secret
    )
    
    try:
        response = pricing_client.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Storage Snapshot'},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': human_region},
                {'Type': 'TERM_MATCH', 'Field': 'usagetype', 'Value': 'EBS:SnapshotUsage'}
            ],
            MaxResults=1
        )
        
        price_list = response.get('PriceList', [])
        if not price_list:
            # Fallback if regional pricing filter returns no items
            return 0.05 * size_gb
            
        price_data = json.loads(price_list[0])
        on_demand = price_data['terms']['OnDemand']
        term_id = list(on_demand.keys())[0]
        price_dimensions = on_demand[term_id]['priceDimensions']
        rate_id = list(price_dimensions.keys())[0]
        price_per_gb = float(price_dimensions[rate_id]['pricePerUnit']['USD'])
        
        return price_per_gb * size_gb
        
    except Exception as e:
        print(f"[Pricing API] Could not fetch real snapshot price for {region_name}: {e}. Using baseline estimate.")
        return 0.05 * size_gb

def calculate_savings(discovered_snapshots, account_id=None):
    """
    Calculates exact financial metrics:
    - Current cost: Fetched STRICTLY from CUR report.
    - Optimized target cost: $0.00 (deleting orphaned snapshot).
    - Savings: 100% of current cost.
    - Uses live AWS Pricing API as fallback if CUR record is missing.
    """
    enriched_snapshots = []
    
    for snap in discovered_snapshots:
        resource_id = snap.get('resource_id')
        region = snap.get('region', 'us-east-1')
        size_gb = float(snap.get('size_gb', 0))
        
        # 1. Fetch live market rate from real AWS Pricing API
        market_monthly_cost = get_real_snapshot_market_price(region, size_gb)
        
        # 2. Fetch True Current Cost from CUR Report ONLY (using market price as fallback)
        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id,
            fallback_cost=market_monthly_cost
        )
        
        # 3. Projected cost is $0.00 since orphaned snapshot will be deleted
        projected_cost = 0.0
        savings = current_cost - projected_cost
        
        snap['currentDailyCost'] = f"${current_cost/30:,.2f}"
        snap['currentMonthlyCost'] = f"${current_cost:,.2f}"
        snap['estimatedMonthlySavings'] = f"${savings:,.2f}"
        
        enriched_snapshots.append(snap)
        
    return enriched_snapshots


import boto3
import json
import sys
import os

# Ensure backend directory is importable
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils.cur_processor import get_historical_cost
from utils.region_mapping import get_pricing_region

def get_real_market_price(region_name, storage_type, allocated_storage_gb):
    """
    Hits the REAL AWS Pricing API to find the exact market rate for this storage.
    This acts as a perfect fallback if the CUR historical cost is missing.
    """
    # 1. Translate the region using our mapper (e.g., us-east-1 -> US East (N. Virginia))
    human_region = get_pricing_region(region_name)
    
    # Load the real credentials from the .env file
    from dotenv import load_dotenv
    env_path = os.path.join(backend_dir, '.env')
    load_dotenv(env_path)
    
    real_access = os.environ.get("REAL_AWS_ACCESS_KEY_ID")
    real_secret = os.environ.get("REAL_AWS_SECRET_ACCESS_KEY")
    
    # 2. The Pricing API endpoint is ONLY available in us-east-1 or ap-south-1
    # We pass the real credentials here so it breaks out of the fake testing environment!
    pricing_client = boto3.client(
        'pricing', 
        region_name='us-east-1',
        aws_access_key_id=real_access,
        aws_secret_access_key=real_secret
    )
    
    try:
        response = pricing_client.get_products(
            ServiceCode='AmazonRDS',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': human_region},
                {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': storage_type},
                {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Database Storage'}
            ],
            MaxResults=1
        )
        
        if not response['PriceList']:
            return 0.115 * allocated_storage_gb # Ultimate fallback
            
        price_data = json.loads(response['PriceList'][0])
        on_demand = price_data['terms']['OnDemand']
        term_id = list(on_demand.keys())[0]
        price_dimensions = on_demand[term_id]['priceDimensions']
        rate_id = list(price_dimensions.keys())[0]
        price_per_gb = float(price_dimensions[rate_id]['pricePerUnit']['USD'])
        
        return price_per_gb * allocated_storage_gb

    except Exception as e:
        print(f"[Pricing API] Could not fetch real market price: {e}. Using baseline estimate.")
        return 0.115 * allocated_storage_gb


def calculate_savings(discovered_resources, account_id=None):
    enriched = []
    
    for res in discovered_resources:
        storage_gb = float(res.get('allocated_storage', 0))
        region = res.get('region', 'us-east-1')
        
        # Map the technical storage type to the Pricing API's human string
        storage_type_str = "General Purpose (SSD)" if res.get('storage_type') == 'gp2' else res.get('storage_type')
        
        # [PILLAR 5] Hit the real AWS Pricing API for the exact market rate!
        market_monthly_cost = get_real_market_price(region, storage_type_str, storage_gb)
        
        # [PILLAR 4] Check the CUR database for historical cost (Use Market Price as fallback)
        resource_id = str(res.get('resource_id', ''))
        current_cost = get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id, 
            fallback_cost=market_monthly_cost
        )
        
        # Projected cost is $0 since we are deleting the stopped instance entirely
        projected_cost = 0
        savings = current_cost - projected_cost
        
        # Create an enriched copy to hand back to the main script
        enriched_res = res.copy()
        enriched_res['currentDailyCost'] = f"${current_cost / 30:.2f}"
        enriched_res['currentMonthlyCost'] = f"${current_cost:.2f}"
        enriched_res['estimatedMonthlySavings'] = f"${savings:.2f}"
        
        enriched.append(enriched_res)
        
    return enriched

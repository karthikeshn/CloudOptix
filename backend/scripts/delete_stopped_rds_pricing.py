import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import the get_historical_cost function from the CUR backend
from utils.cur_processor import get_historical_cost

def calculate_savings(discovered_resources, account_id=None):
    enriched = []
    for res in discovered_resources:
        # Fallback pricing: roughly $0.115/GB-month for gp2/gp3 RDS storage
        # Stopped RDS instances still charge for storage and backups.
        storage_gb = float(res.get('allocated_storage', 0) or 0)
        fallback_monthly_cost = storage_gb * 0.115
        
        # We fetch the true historical cost from the CUR billing file!
        resource_id = str(res.get('instance_id', res.get('resource_id', '')))
        current_cost = get_historical_cost(resource_id=resource_id, account_id=account_id, fallback_cost=fallback_monthly_cost)
        
        # Projected cost is $0 since we are deleting the stopped instance entirely
        projected_cost = 0
        savings = current_cost - projected_cost
        
        # Create an enriched copy of the dictionary
        enriched_res = res.copy()
        enriched_res['currentDailyCost'] = f"${current_cost / 30:.2f}"
        enriched_res['currentMonthlyCost'] = f"${current_cost:.2f}"
        enriched_res['estimatedMonthlySavings'] = f"${savings:.2f}"
        
        enriched.append(enriched_res)
        
    return enriched

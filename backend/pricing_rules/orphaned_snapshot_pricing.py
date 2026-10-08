import sys
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_processor as cur_integration
from utils import aws_pricing

def calculate_savings(discovered_snapshots, account_id=None):
    """
    Takes a list of discovered orphaned snapshots and calculates the exact financial metrics.
    Expected snapshot dictionary keys:
    - resource_id (e.g., snap-1234abcd)
    - region (e.g., us-east-1)
    - size_gb (int)
    """
    enriched_snapshots = []
    
    for snap in discovered_snapshots:
        resource_id = snap.get('resource_id')
        region = snap.get('region', 'us-east-1')
        size_gb = float(snap.get('size_gb', 0))
        
        # Calculate Fallback Current Cost (if CUR is missing)
        rates = aws_pricing.get_ebs_snapshot_rates(region)
        fallback_current_cost = size_gb * rates['storage_rate']
        
        # Get True Current Cost from CUR
        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id,
            fallback_cost=fallback_current_cost
        )
        
        savings = current_cost
        
        snap['currentDailyCost'] = f"${current_cost/30:,.2f}"
        snap['currentMonthlyCost'] = f"${current_cost:,.2f}"
        snap['estimatedMonthlySavings'] = f"${savings:,.2f}"
        
        enriched_snapshots.append(snap)
        
    return enriched_snapshots

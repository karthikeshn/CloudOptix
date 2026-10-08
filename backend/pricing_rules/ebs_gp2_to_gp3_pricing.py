import sys
import os

# Add the backend root to the path so we can import utils
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_integration
from utils import aws_pricing

def calculate_savings(discovered_volumes, account_id=None):
    """
    Takes a list of discovered gp2 volumes and calculates the exact financial metrics.
    Expected volume dictionary keys: 
    - resource_id (e.g., vol-1234abcd)
    - region (e.g., us-east-1)
    - size_gb (int)
    - iops (int, optional, gp2 defaults to size * 3)
    - throughput_mbps (int, optional, gp2 maxes at 250)
    """
    enriched_volumes = []
    
    for vol in discovered_volumes:
        resource_id = vol.get('resource_id')
        region = vol.get('region', 'us-east-1')
        size_gb = float(vol.get('size_gb', 0))
        
        # GP2 baseline metrics
        # GP2 IOPS: 3 IOPS per GB (min 100, max 16000)
        current_iops = vol.get('iops')
        if not current_iops:
            current_iops = max(100, min(size_gb * 3, 16000))
            
        # GP2 Throughput: generally up to 250 MiB/s
        current_throughput = vol.get('throughput_mbps')
        if not current_throughput:
            current_throughput = 250
        
        # 1. Fetch Rates
        gp2_rates = aws_pricing.get_ebs_gp2_rates(region)
        gp3_rates = aws_pricing.get_ebs_gp3_rates(region)
        
        # 2. Calculate Fallback Current Cost (if CUR is missing)
        fallback_current_cost = size_gb * gp2_rates['storage_rate']
        
        # 3. Get True Current Cost from CUR (using fallback if not found)
        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id,
            fallback_cost=fallback_current_cost
        )
        
        # 4. Calculate Projected GP3 Cost
        # GP3 base storage cost
        projected_storage_cost = size_gb * gp3_rates['storage_rate']
        
        # GP3 extra IOPS cost (first 3000 are free)
        billable_iops = max(0, current_iops - 3000)
        projected_iops_cost = billable_iops * gp3_rates['iops_rate']
        
        # GP3 extra throughput cost (first 125 MB/s are free)
        billable_throughput = max(0, current_throughput - 125)
        projected_throughput_cost = billable_throughput * gp3_rates['throughput_rate']
        
        projected_cost = projected_storage_cost + projected_iops_cost + projected_throughput_cost
        
        # 5. Calculate Savings
        savings = current_cost - projected_cost
        
        # If somehow savings is negative, it's not an optimization, so cap at 0
        if savings < 0:
            savings = 0.0
            
        # 6. Mutate the original dictionary with standardized financial columns
        vol['currentDailyCost'] = f"${current_cost/30:,.2f}"
        vol['currentMonthlyCost'] = f"${current_cost:,.2f}"
        vol['estimatedMonthlySavings'] = f"${savings:,.2f}"
        
        enriched_volumes.append(vol)
        
    return enriched_volumes

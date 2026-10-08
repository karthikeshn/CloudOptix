import sys
import os

# Add the backend root to the path so we can import utils
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_processor as cur_integration
from utils import aws_pricing






def calculate_savings(discovered_volumes, account_id=None):
    """
    Takes a list of discovered unattached volumes and calculates the exact financial metrics.
    Expected volume dictionary keys: 
    - resource_id (e.g., vol-1234abcd)
    - region (e.g., us-east-1)
    - size_gb (int)
    - volume_type (str, e.g., gp2, gp3)
    """
    enriched_volumes = []
    
    for vol in discovered_volumes:
        resource_id = vol.get('resource_id')
        region = vol.get('region', 'us-east-1')
        size_gb = float(vol.get('size_gb', 0))
        volume_type = vol.get('volume_type', 'gp2')
        
        # Calculate Fallback Current Cost (if CUR is missing)
        # We handle gp2, gp3, and other specialized volume types
        if volume_type == 'gp3':
            rates = aws_pricing.get_ebs_gp3_rates(region)
            fallback_current_cost = size_gb * rates['storage_rate']
        elif volume_type == 'gp2':
            rates = aws_pricing.get_ebs_gp2_rates(region)
            fallback_current_cost = size_gb * rates['storage_rate']
        else:
            rates = aws_pricing.get_ebs_other_rates(region, volume_type)
            fallback_current_cost = size_gb * rates['storage_rate']
            
        # Get True Current Cost from CUR (using fallback if not found)
        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id,
            fallback_cost=fallback_current_cost
        )
        
        # Since this is a Deletion action, the projected cost is exactly $0.00
        projected_cost = 0.0
        
        # The savings is 100% of the current cost
        savings = current_cost
        
        # Mutate the original dictionary with standardized financial columns
        vol['currentDailyCost'] = f"${current_cost/30:,.2f}"
        vol['currentMonthlyCost'] = f"${current_cost:,.2f}"
        vol['estimatedMonthlySavings'] = f"${savings:,.2f}"
        
        enriched_volumes.append(vol)
        
    return enriched_volumes

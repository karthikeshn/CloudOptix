import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from utils import cur_processor as cur_integration

def calculate_savings(discovered_instances, account_id=None):
    """
    Takes a list of instances eligible for Graviton migration and calculates financial metrics.
    Expected instance dictionary keys:
    - resource_id (e.g., i-1234abcd)
    - region (e.g., us-east-1)
    - instance_type (e.g., m5.large)
    """
    enriched_instances = []
    
    for instance in discovered_instances:
        resource_id = instance.get('resource_id')
        region = instance.get('region', 'us-east-1')
        instance_type = instance.get('instance_type', 'unknown')
        
        # Fallback current cost estimation (assumes roughly $0.10 per hour for generic fallback)
        fallback_current_cost = 0.10 * 730  # Approx $73.00/month fallback
        
        # Get True Current Cost from CUR
        current_cost = cur_integration.get_historical_cost(
            resource_id=resource_id, 
            account_id=account_id,
            fallback_cost=fallback_current_cost
        )
        
        # Graviton instances generally offer ~20% price performance savings over comparable x86 instances
        savings = current_cost * 0.20
        
        instance['currentDailyCost'] = f"${current_cost/30:,.2f}"
        instance['currentMonthlyCost'] = f"${current_cost:,.2f}"
        instance['estimatedMonthlySavings'] = f"${savings:,.2f}"
        
        enriched_instances.append(instance)
        
    return enriched_instances

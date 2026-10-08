import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from app.models.control.control_resource import ServiceType, ControlType
import json

logger = logging.getLogger(__name__)

def discover_beanstalk_environments(session, region: str) -> List[Dict[str, Any]]:
    """
    Scans Elastic Beanstalk applications and environments.
    Groups environments under their respective applications.
    Also queries the underlying EnvironmentResources to find the ASG name.
    """
    resources = []
    client = session.client('elasticbeanstalk', region_name=region)
    
    try:
        seen_apps = set()
        
        next_token = None
        while True:
            params = {'IncludeDeleted': False}
            if next_token:
                params['NextToken'] = next_token
                
            env_res = client.describe_environments(**params)
        
            for env in env_res.get('Environments', []):
                env_name = env['EnvironmentName']
                app_name = env['ApplicationName']
                status = env['Status']
                health = env.get('Health', 'Unknown')
                tier = env.get('Tier', {}).get('Name', 'Unknown')
                
                # Skip terminated envs to match original logic
                if status in ['Terminated', 'Terminating']:
                    continue
                
                # Emit Application parent dynamically
                if app_name and app_name not in seen_apps:
                    seen_apps.add(app_name)
                    resources.append({
                        'resource_id': app_name,
                        'resource_name': app_name,
                        'cloud_provider': 'aws',
                        'region': region,
                        'service_type': ServiceType.BEANSTALK.value,
                        'control_type': ControlType.SCALE_TO_ZERO.value,
                        'status': 'UNKNOWN',
                        'instance_spec': 'Application (Parent Container)',
                        'tags': {},
                        'parent_resource_id': None,
                        'last_synced_at': datetime.now(timezone.utc)
                    })
                
                # Attempt to find the underlying ASG name for this environment
                asg_name = None
                desired_cap = None
                try:
                    env_resources = client.describe_environment_resources(EnvironmentName=env_name)
                    asgs = env_resources.get('EnvironmentResources', {}).get('AutoScalingGroups', [])
                    if asgs:
                        asg_name = asgs[0].get('Name')
                        # Query ASG capacity to determine true power state
                        autoscaling = session.client('autoscaling', region_name=region)
                        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
                        groups = asg_res.get('AutoScalingGroups', [])
                        if groups:
                            desired_cap = groups[0].get('DesiredCapacity', 0)
                except Exception as e:
                    logger.debug(f"Failed to find ASG for Beanstalk Environment {env_name}: {e}")

                # Map EB status to our standard status
                mapped_status = 'UNKNOWN'
                if status == 'Ready':
                    if desired_cap is not None and desired_cap == 0:
                        mapped_status = 'STOPPED'
                    else:
                        mapped_status = 'RUNNING'
                elif status in ['Launching', 'Updating']:
                    mapped_status = 'STARTING'
                    
                spec = f"Tier: {tier} | Health: {health}"
                
                # Save the asg_name in the config payload for flow tracking
                config_payload = {}
                if asg_name:
                    config_payload['asg_name'] = asg_name
                    spec = f"ASG: {asg_name} | {spec}"
                    
                saved_config = json.dumps(config_payload) if config_payload else None
                
                resources.append({
                    'resource_id': env_name,
                    'resource_name': env_name,
                    'cloud_provider': 'aws',
                    'region': region,
                    'service_type': ServiceType.BEANSTALK.value,
                    'control_type': ControlType.SCALE_TO_ZERO.value,
                    'status': mapped_status,
                    'instance_spec': spec,
                    'tags': {},
                    'parent_resource_id': app_name,
                    'saved_config_json': saved_config,
                    'last_synced_at': datetime.now(timezone.utc)
                })

            next_token = env_res.get('NextToken')
            if not next_token:
                break

    except Exception as e:
        logger.error(f"Error scanning Beanstalk resources in {region}: {e}")

    return resources

import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from app.services.base_handler import BaseScaleToZeroHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

class BeanstalkHandler(BaseScaleToZeroHandler):
    """
    AWS Elastic Beanstalk Plugin Handler.
    Implements Scale-to-Zero for Beanstalk environments by targeting underlying ASG.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('elasticbeanstalk')
        autoscaling = session.client('autoscaling')
        
        # Describe environment
        res = client.describe_environments(EnvironmentNames=[native_id], IncludeDeleted=False)
        envs = res.get('Environments', [])
        if not envs:
            return 'UNKNOWN'
            
        env = envs[0]
        env_status = env.get('Status')
        
        if env_status in ['Updating', 'Launching']:
            return 'TRANSITIONING'
            
        # We need to find the ASG to see desired capacity
        resources_res = client.describe_environment_resources(EnvironmentName=native_id)
        asgs = resources_res.get('EnvironmentResources', {}).get('AutoScalingGroups', [])
        
        if not asgs:
            return 'UNKNOWN'
            
        asg_name = asgs[0].get('Name')
        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = asg_res.get('AutoScalingGroups', [])
        
        if not groups:
            return 'UNKNOWN'
            
        desired_cap = groups[0].get('DesiredCapacity', 0)
        
        if env_status == 'Ready':
            if desired_cap > 0:
                return 'RUNNING'
            else:
                return 'STOPPED'
                
        return 'UNKNOWN'

    def _execute_stop(self, session, native_id: str, **kwargs) -> str:
        client = session.client('elasticbeanstalk')
        autoscaling = session.client('autoscaling')
        
        # Get ASG info
        resources_res = client.describe_environment_resources(EnvironmentName=native_id)
        asgs = resources_res.get('EnvironmentResources', {}).get('AutoScalingGroups', [])
        
        if not asgs:
            raise Exception(f"No ASG found for Beanstalk environment {native_id}")
            
        asg_name = asgs[0].get('Name')
        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = asg_res.get('AutoScalingGroups', [])
        
        if not groups:
            raise Exception(f"ASG {asg_name} not found")
            
        min_size = groups[0].get('MinSize', 0)
        desired_cap = groups[0].get('DesiredCapacity', 0)
        
        config = {
            "minSize": min_size,
            "desiredCapacity": desired_cap,
            "asg_name": asg_name
        }
        
        autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=0,
            DesiredCapacity=0
        )
        
        return json.dumps(config)

    def _execute_start(self, session, native_id: str, saved_config: str, **kwargs):
        autoscaling = session.client('autoscaling')
        
        target_min = 1
        target_desired = 1
        asg_name = None
        
        if saved_config:
            try:
                parsed_config = json.loads(saved_config)
                target_min = parsed_config.get('minSize', 1)
                target_desired = parsed_config.get('desiredCapacity', 1)
                asg_name = parsed_config.get('asg_name') or parsed_config.get('asgName')
            except Exception as e:
                logger.warning(f"Failed to parse saved config for Beanstalk {native_id}: {e}")
                
        if not asg_name:
            client = session.client('elasticbeanstalk')
            resources_res = client.describe_environment_resources(EnvironmentName=native_id)
            asgs = resources_res.get('EnvironmentResources', {}).get('AutoScalingGroups', [])
            if asgs:
                asg_name = asgs[0].get('Name')
                
        if asg_name:
            # Prevent zero lock
            if target_min == 0:
                target_min = 1
            if target_desired == 0:
                target_desired = 1
                
            autoscaling.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=target_min,
                DesiredCapacity=target_desired
            )
        else:
            logger.error(f"Cannot start Beanstalk {native_id} because ASG name is unknown.")

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        from app.services.aws.discovery.beanstalk_discovery import discover_beanstalk_environments
        return discover_beanstalk_environments(session, region)

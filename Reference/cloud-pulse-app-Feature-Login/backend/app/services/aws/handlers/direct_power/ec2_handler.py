import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from botocore.exceptions import ClientError

from app.services.base_handler import BaseDirectPowerHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

def normalize_ec2_status(state_name: str) -> str:
    state_name = (state_name or "").lower()
    if state_name == "running":
        return "RUNNING"
    elif state_name == "stopped":
        return "STOPPED"
    elif state_name:
        return state_name.upper()
    return "UNKNOWN"

class EC2Handler(BaseDirectPowerHandler):
    
    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('ec2')
        res = client.describe_instances(InstanceIds=[native_id])
        for r in res.get('Reservations', []):
            for inst in r.get('Instances', []):
                return normalize_ec2_status(inst.get('State', {}).get('Name', 'unknown'))
        return 'UNKNOWN'

    def _execute_start(self, session, native_id: str, **kwargs):
        client = session.client('ec2')
        try:
            client.start_instances(InstanceIds=[native_id])
        except ClientError as e:
            err_msg = e.response.get('Error', {}).get('Message', str(e))
            if 'volume attached at root' in err_msg:
                raise ValueError(f"Instance {native_id} is instance-store backed and cannot be started/stopped (only rebooted or terminated).")
            raise ValueError(f"Failed to start EC2 instance: {err_msg}")

    def _execute_stop(self, session, native_id: str, **kwargs):
        client = session.client('ec2')
        try:
            client.stop_instances(InstanceIds=[native_id])
        except ClientError as e:
            err_msg = e.response.get('Error', {}).get('Message', str(e))
            if 'volume attached at root' in err_msg:
                raise ValueError(f"Instance {native_id} is instance-store backed and cannot be stopped (only rebooted or terminated).")
            raise ValueError(f"Failed to stop EC2 instance: {err_msg}")

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        resources = []
        ec2_client = session.client('ec2', region_name=region)
        paginator = ec2_client.get_paginator('describe_instances')
        for page in paginator.paginate():
            for reservation in page.get('Reservations', []):
                for inst in reservation.get('Instances', []):
                    instance_id = inst['InstanceId']
                    state_name = inst.get('State', {}).get('Name', '')
                    
                    if state_name.lower() == 'terminated':
                        continue
                        
                    instance_type = inst.get('InstanceType', 'unknown')
                    
                    resource_name = instance_id
                    tags_dict = {}
                    parent_asg = None
                    for tag in inst.get('Tags', []):
                        tags_dict[tag.get('Key')] = tag.get('Value')
                        if tag.get('Key') == 'Name' and tag.get('Value'):
                            resource_name = tag['Value']
                        if tag.get('Key') == 'aws:autoscaling:groupName' and tag.get('Value'):
                            parent_asg = tag['Value']
                            
                    resources.append({
                        'resource_id': instance_id,
                        'resource_name': resource_name,
                        'cloud_provider': 'aws',
                        'region': region,
                        'service_type': ServiceType.EC2.value,
                        'control_type': ControlType.DIRECT_POWER.value,
                        'status': normalize_ec2_status(state_name),
                        'instance_spec': instance_type,
                        'tags': tags_dict,
                        'parent_resource_id': parent_asg,
                        'last_synced_at': datetime.now(timezone.utc)
                    })
        return resources

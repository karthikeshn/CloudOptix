import json
import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

from app.services.base_handler import BaseScaleToZeroHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

class AppRunnerHandler(BaseScaleToZeroHandler):
    """
    Amazon App Runner Plugin Handler.
    Implements Scale-to-Zero for App Runner services.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('apprunner')
        res = client.describe_service(ServiceArn=native_id)
        status = res.get('Service', {}).get('Status', 'UNKNOWN')
        
        if status == 'RUNNING':
            return 'RUNNING'
        elif status == 'PAUSED':
            return 'STOPPED'
        elif status in ['OPERATION_IN_PROGRESS', 'PENDING_CREATION']:
            return 'TRANSITIONING'
        else:
            return 'STOPPED'

    def _execute_stop(self, session, native_id: str, **kwargs) -> str:
        client = session.client('apprunner')
        client.pause_service(ServiceArn=native_id)
        # App Runner manages scaling capacity internally
        return json.dumps({})

    def _execute_start(self, session, native_id: str, saved_config: str, **kwargs):
        client = session.client('apprunner')
        client.resume_service(ServiceArn=native_id)

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        client = session.client('apprunner', region_name=region)
        resources = []
        next_token = None
        while True:
            kwargs = {}
            if next_token:
                kwargs['NextToken'] = next_token
                
            page = client.list_services(**kwargs)
            
            for service in page.get('ServiceSummaryList', []):
                arn = service.get('ServiceArn')
                name = service.get('ServiceName')
                status_raw = service.get('Status')
                
                if status_raw == 'RUNNING':
                    status = 'RUNNING'
                elif status_raw == 'PAUSED':
                    status = 'STOPPED'
                elif status_raw in ['OPERATION_IN_PROGRESS', 'PENDING_CREATION']:
                    status = 'TRANSITIONING'
                else:
                    status = 'STOPPED'
                    
                resources.append({
                    'resource_id': arn,
                    'resource_name': name,
                    'cloud_provider': 'aws',
                    'region': region,
                    'service_type': ServiceType.APP_RUNNER.value,
                    'control_type': ControlType.SCALE_TO_ZERO.value,
                    'status': status,
                    'instance_spec': 'App Runner Service',
                    'tags': {},
                    'parent_resource_id': None,
                    'last_synced_at': datetime.now(timezone.utc)
                })
            
            next_token = page.get('NextToken')
            if not next_token:
                break
                
        return resources

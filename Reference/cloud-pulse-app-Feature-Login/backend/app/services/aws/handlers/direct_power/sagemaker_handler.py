from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
from botocore.exceptions import ClientError
from app.services.base_handler import BaseDirectPowerHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

def normalize_sagemaker_status(state_name: str) -> str:
    state_name = (state_name or "").lower()
    if state_name == "inservice":
        return "RUNNING"
    elif state_name == "stopped":
        return "STOPPED"
    elif state_name:
        return state_name.upper()
    return "UNKNOWN"

class SageMakerHandler(BaseDirectPowerHandler):
    """
    AWS SageMaker Plugin Handler.
    Implements Discovery and Direct Power control for SageMaker Notebook Instances.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('sagemaker')
        res = client.describe_notebook_instance(NotebookInstanceName=native_id)
        return normalize_sagemaker_status(res.get('NotebookInstanceStatus', 'unknown'))

    def _execute_start(self, session, native_id: str, **kwargs):
        client = session.client('sagemaker')
        client.start_notebook_instance(NotebookInstanceName=native_id)

    def _execute_stop(self, session, native_id: str, **kwargs):
        client = session.client('sagemaker')
        client.stop_notebook_instance(NotebookInstanceName=native_id)

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        resources = []
        client = session.client('sagemaker', region_name=region)
        paginator = client.get_paginator('list_notebook_instances')
        for page in paginator.paginate():
            for nb in page.get('NotebookInstances', []):
                resources.append({
                    'resource_id': nb['NotebookInstanceName'],
                    'resource_name': nb['NotebookInstanceName'],
                    'cloud_provider': 'aws',
                    'region': region,
                    'service_type': ServiceType.SAGEMAKER.value,
                    'control_type': ControlType.DIRECT_POWER.value,
                    'status': normalize_sagemaker_status(nb.get('NotebookInstanceStatus', 'unknown')),
                    'instance_spec': nb.get('InstanceType', 'unknown'),
                    'tags': {},
                    'last_synced_at': datetime.now(timezone.utc)
                })

        return resources

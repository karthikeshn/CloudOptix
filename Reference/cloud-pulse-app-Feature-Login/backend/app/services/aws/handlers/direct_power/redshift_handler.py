from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
from botocore.exceptions import ClientError
from app.services.base_handler import BaseDirectPowerHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

def normalize_redshift_status(state_name: str) -> str:
    state_name = (state_name or "").lower()
    if state_name == "available":
        return "RUNNING"
    elif state_name == "paused":
        return "STOPPED"
    elif state_name:
        return state_name.upper()
    return "UNKNOWN"

class RedshiftHandler(BaseDirectPowerHandler):
    """
    AWS Redshift Plugin Handler.
    Implements Discovery and Direct Power control for Redshift Clusters.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('redshift')
        res = client.describe_clusters(ClusterIdentifier=native_id)
        clusters = res.get('Clusters', [])
        if clusters:
            return normalize_redshift_status(clusters[0].get('ClusterStatus', 'unknown'))
        return "UNKNOWN"

    def _execute_start(self, session, native_id: str, **kwargs):
        client = session.client('redshift')
        client.resume_cluster(ClusterIdentifier=native_id)

    def _execute_stop(self, session, native_id: str, **kwargs):
        client = session.client('redshift')
        client.pause_cluster(ClusterIdentifier=native_id)

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        resources = []
        client = session.client('redshift', region_name=region)
        
        marker = None
        while True:
            params = {}
            if marker:
                params['Marker'] = marker
                
            clusters_res = client.describe_clusters(**params)
            for cluster in clusters_res.get('Clusters', []):
                tags_list = cluster.get('Tags', [])
                tags_dict = {t.get('Key'): t.get('Value') for t in tags_list}

                resources.append({
                    'resource_id': cluster['ClusterIdentifier'],
                    'resource_name': cluster['ClusterIdentifier'],
                    'cloud_provider': 'aws',
                    'region': region,
                    'service_type': ServiceType.REDSHIFT.value,
                    'control_type': ControlType.DIRECT_POWER.value,
                    'status': normalize_redshift_status(cluster.get('ClusterStatus', 'unknown')),
                    'instance_spec': cluster.get('NodeType', 'unknown'),
                    'tags': tags_dict,
                    'last_synced_at': datetime.now(timezone.utc)
                })
                
            marker = clusters_res.get('Marker')
            if not marker:
                break

        return resources

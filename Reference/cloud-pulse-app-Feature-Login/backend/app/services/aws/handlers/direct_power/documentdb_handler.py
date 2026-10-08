from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
from botocore.exceptions import ClientError
from app.services.base_handler import BaseDirectPowerHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

def normalize_docdb_status(state_name: str) -> str:
    state_name = (state_name or "").lower()
    if state_name == "available":
        return "RUNNING"
    elif state_name == "stopped":
        return "STOPPED"
    elif state_name:
        return state_name.upper()
    return "UNKNOWN"

class DocumentDBHandler(BaseDirectPowerHandler):
    """
    AWS DocumentDB Plugin Handler.
    Implements Discovery and Direct Power control for DocumentDB Clusters.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('docdb')
        res = client.describe_db_clusters(DBClusterIdentifier=native_id)
        clusters = res.get('DBClusters', [])
        if clusters:
            return normalize_docdb_status(clusters[0].get('Status', 'unknown'))
        return "UNKNOWN"

    def _execute_start(self, session, native_id: str, **kwargs):
        client = session.client('docdb')
        client.start_db_cluster(DBClusterIdentifier=native_id)

    def _execute_stop(self, session, native_id: str, **kwargs):
        client = session.client('docdb')
        client.stop_db_cluster(DBClusterIdentifier=native_id)

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        resources = []
        client = session.client('docdb', region_name=region)
        
        marker = None
        while True:
            params = {}
            if marker:
                params['Marker'] = marker
                
            clusters_res = client.describe_db_clusters(**params)
            for cluster in clusters_res.get('DBClusters', []):
                if cluster.get('Engine') != 'docdb':
                    continue

                tags_list = cluster.get('TagList', [])
                tags_dict = {t.get('Key'): t.get('Value') for t in tags_list}

                resources.append({
                    'resource_id': cluster['DBClusterIdentifier'],
                    'resource_name': cluster['DBClusterIdentifier'],
                    'cloud_provider': 'aws',
                    'region': region,
                    'service_type': ServiceType.DOCUMENTDB.value,
                    'control_type': ControlType.DIRECT_POWER.value,
                    'status': normalize_docdb_status(cluster.get('Status', 'unknown')),
                    'instance_spec': 'cluster',
                    'tags': tags_dict,
                    'last_synced_at': datetime.now(timezone.utc)
                })
                
            marker = clusters_res.get('Marker')
            if not marker:
                break

        return resources

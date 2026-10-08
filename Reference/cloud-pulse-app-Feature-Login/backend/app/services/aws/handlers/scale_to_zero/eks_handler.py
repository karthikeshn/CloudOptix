from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
import json
from botocore.exceptions import ClientError
from app.services.base_handler import BaseScaleToZeroHandler
from app.models.control.control_resource import ServiceType, ControlType

logger = logging.getLogger(__name__)

class EKSHandler(BaseScaleToZeroHandler):
    """
    AWS EKS (Elastic Kubernetes Service) Plugin Handler.
    Implements Discovery and Scale-to-Zero lifecycle control for Managed Node Groups.
    Parent: EKS Cluster
    Child: EKS Managed Node Group
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        client = session.client('eks')
        # native_id is expected to be in the format "cluster_name/nodegroup_name"
        # However, for EKS Auto Mode, it is just "cluster_name"
        if '/' not in native_id:
            return "RUNNING"  # EKS Auto Mode clusters are always considered running since they scale dynamically
            
        try:
            cluster_name, nodegroup_name = native_id.split('/', 1)
            res = client.describe_nodegroup(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name
            )
            nodegroup = res.get('nodegroup', {})
            status = nodegroup.get('status')
            scaling_config = nodegroup.get('scalingConfig', {})
            desired = scaling_config.get('desiredSize', 0)
            
            if status in ['CREATING', 'UPDATING']:
                return "STARTING" if desired > 0 else "STOPPING"
            elif status == 'DELETING':
                return "STOPPING"
            elif status == 'ACTIVE':
                return "RUNNING" if desired > 0 else "STOPPED"
            elif status in ['DEGRADED', 'ACTIVE_DEGRADED']:
                return "RUNNING" if desired > 0 else "STOPPED"
                
            return "UNKNOWN"
        except Exception as e:
            logger.warning(f"[EKSHandler] Error getting state for {native_id}: {e}")
            return "UNKNOWN"

    def _execute_start(self, session, native_id: str, saved_config: str, **kwargs):
        client = session.client('eks')
        
        if '/' not in native_id:
            cluster_name = native_id
            nodegroup_name = None
        else:
            cluster_name, nodegroup_name = native_id.split('/', 1)
            
        try:
            cluster_res = client.describe_cluster(name=cluster_name)
            if cluster_res.get('cluster', {}).get('computeConfig', {}).get('enabled', False):
                raise Exception("Scale-to-zero is handled natively by EKS Auto Mode. To reduce compute to 0, scale Kubernetes deployment replicas to 0.")
        except ClientError:
            pass
            
        if not nodegroup_name:
            raise Exception("Cannot start an EKS cluster without a nodegroup unless it's EKS Auto Mode.")
        
        # Default back to 1 if no config was saved
        config = {"minSize": 1, "desiredSize": 1}
        if saved_config:
            try:
                config = json.loads(saved_config)
            except:
                pass
                
        prev_min = config.get('minSize', 1)
        prev_desired = config.get('desiredSize', 1)
        prev_max = config.get('maxSize', max(prev_desired, 1))
        
        if config.get('unmanaged_asgs'):
            autoscaling = session.client('autoscaling')
            for asg_state in config['unmanaged_asgs']:
                try:
                    autoscaling.update_auto_scaling_group(
                        AutoScalingGroupName=asg_state['name'],
                        MinSize=asg_state['min'],
                        DesiredCapacity=asg_state['desired'],
                        MaxSize=asg_state.get('max', max(asg_state['desired'], 1))
                    )
                except Exception as e:
                    logger.warning(f"Failed to restore unmanaged ASG {asg_state['name']}: {e}")
                    
        try:
            client.update_nodegroup_config(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name,
                scalingConfig={
                    'minSize': prev_min,
                    'desiredSize': prev_desired,
                    'maxSize': prev_max
                }
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                raise Exception("EKS Managed Node Group is currently updating. Please try again later.")
            raise e

    def _execute_stop(self, session, native_id: str, **kwargs) -> str:
        client = session.client('eks')
        
        if '/' not in native_id:
            # It's an EKS Auto Mode cluster directly, or a malformed ID
            cluster_name = native_id
            nodegroup_name = None
        else:
            cluster_name, nodegroup_name = native_id.split('/', 1)
            
        try:
            cluster_res = client.describe_cluster(name=cluster_name)
            if cluster_res.get('cluster', {}).get('computeConfig', {}).get('enabled', False):
                raise Exception("Scale-to-zero is handled natively by EKS Auto Mode. To reduce compute to 0, scale Kubernetes deployment replicas to 0.")
        except ClientError:
            pass
            
        if not nodegroup_name:
            raise Exception("Cannot stop an EKS cluster without a nodegroup unless it's EKS Auto Mode.")
            
        res = client.describe_nodegroup(
            clusterName=cluster_name,
            nodegroupName=nodegroup_name
        )
        nodegroup = res.get('nodegroup', {})
        scaling_config = nodegroup.get('scalingConfig', {})
        
        current_min = scaling_config.get('minSize', 0)
        current_desired = scaling_config.get('desiredSize', 0)
        current_max = scaling_config.get('maxSize', max(current_desired, 1))
        
        from app.services.aws.discovery.eks_discovery import discover_eks_asgs_and_karpenter
        
        unmanaged_asgs, has_karpenter = discover_eks_asgs_and_karpenter(session, cluster_name)
        
        asg_states = []
        if unmanaged_asgs:
            autoscaling = session.client('autoscaling')
            for a_name in unmanaged_asgs:
                try:
                    asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[a_name])
                    groups = asg_res.get('AutoScalingGroups', [])
                    if groups:
                        g = groups[0]
                        asg_states.append({
                            "name": a_name,
                            "min": g.get('MinSize', 0),
                            "desired": g.get('DesiredCapacity', 0),
                            "max": g.get('MaxSize', 1)
                        })
                        
                        autoscaling.update_auto_scaling_group(
                            AutoScalingGroupName=a_name,
                            MinSize=0,
                            DesiredCapacity=0
                        )
                except Exception as e:
                    logger.warning(f"Failed to stop unmanaged EKS ASG {a_name}: {e}")
        
        asg_name = None
        resources = nodegroup.get('resources', {})
        if resources and resources.get('autoScalingGroups'):
            asg_name = resources['autoScalingGroups'][0].get('name')
        
        saved_config_obj = {
            "minSize": current_min if current_desired > 0 else 1,
            "desiredSize": current_desired if current_desired > 0 else 1,
            "maxSize": current_max,
            "unmanaged_asgs": asg_states,
            "has_karpenter": has_karpenter,
            "asg_name": asg_name
        }
        
        saved_config = json.dumps(saved_config_obj)
            
        try:
            client.update_nodegroup_config(
                clusterName=cluster_name,
                nodegroupName=nodegroup_name,
                scalingConfig={
                    'minSize': 0,
                    'desiredSize': 0
                }
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                raise Exception("EKS Managed Node Group is currently updating. Please try again later.")
            raise e
        
        return saved_config

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        resources = []
        try:
            client = session.client('eks', region_name=region)
            
            # Loop through Parent clusters using list_clusters() paginator.
            cluster_paginator = client.get_paginator('list_clusters')
            for cluster_page in cluster_paginator.paginate():
                for cluster_name in cluster_page.get('clusters', []):
                    try:
                        cluster_res = client.describe_cluster(name=cluster_name)
                        cluster_info = cluster_res.get('cluster', {})
                        
                        is_auto_mode = cluster_info.get('computeConfig', {}).get('enabled', False)
                        
                        if is_auto_mode:
                            resources.append({
                                'resource_id': cluster_name,
                                'resource_name': cluster_name,
                                'cloud_provider': 'aws',
                                'region': region,
                                'service_type': ServiceType.EKS.value,
                                'control_type': ControlType.SCALE_TO_ZERO.value,
                                'status': 'RUNNING',
                                'instance_spec': 'EKS Auto Mode',
                                'tags': cluster_info.get('tags', {}),
                                'parent_resource_id': None,
                                'last_synced_at': datetime.now(timezone.utc),
                                'compute_mode': 'EKS_AUTO_MODE',
                                'scale_to_zero_eligible': False
                            })
                            continue
                            
                        # Emit the standard EKS cluster as a parent resource so children can group under it
                        resources.append({
                            'resource_id': cluster_name,
                            'resource_name': cluster_name,
                            'cloud_provider': 'aws',
                            'region': region,
                            'service_type': ServiceType.EKS.value,
                            'control_type': ControlType.SCALE_TO_ZERO.value,
                            'status': cluster_info.get('status', 'RUNNING'),
                            'instance_spec': f"EKS Cluster (k8s {cluster_info.get('version', 'unknown')})",
                            'tags': cluster_info.get('tags', {}),
                            'parent_resource_id': None,
                            'last_synced_at': datetime.now(timezone.utc),
                            'compute_mode': 'STANDARD',
                            'scale_to_zero_eligible': False
                        })
                            
                    except ClientError as e:
                        logger.warning(f"[EKSHandler] Error describing cluster {cluster_name}: {e}")
                        
                    # For each cluster, enumerate Child node groups
                    try:
                        nodegroup_paginator = client.get_paginator('list_nodegroups')
                        for ng_page in nodegroup_paginator.paginate(clusterName=cluster_name):
                            for ng_name in ng_page.get('nodegroups', []):
                                try:
                                    res = client.describe_nodegroup(
                                        clusterName=cluster_name,
                                        nodegroupName=ng_name
                                    )
                                    ng = res.get('nodegroup', {})
                                    
                                    scaling_config = ng.get('scalingConfig', {})
                                    desired = scaling_config.get('desiredSize', 0)
                                    min_size = scaling_config.get('minSize', 0)
                                    max_size = scaling_config.get('maxSize', 0)
                                    status = ng.get('status', 'UNKNOWN')
                                    
                                    if status in ['CREATING', 'UPDATING']:
                                        mapped_status = 'STARTING' if desired > 0 else 'STOPPING'
                                    elif status == 'DELETING':
                                        mapped_status = 'STOPPING'
                                    elif status in ['ACTIVE', 'DEGRADED', 'ACTIVE_DEGRADED']:
                                        mapped_status = 'RUNNING' if desired > 0 else 'STOPPED'
                                    else:
                                        mapped_status = 'UNKNOWN'
                                        
                                    tags_dict = ng.get('tags', {})
                                    spec = f"Min:{min_size} Max:{max_size} Desired:{desired}"
                                    
                                    # native_id encapsulates both parent and child to allow unique addressing
                                    native_id = f"{cluster_name}/{ng_name}"
                                    
                                    resources.append({
                                        'resource_id': native_id,
                                        'resource_name': ng_name,
                                        'cloud_provider': 'aws',
                                        'region': region,
                                        'service_type': ServiceType.EKS.value,
                                        'control_type': ControlType.SCALE_TO_ZERO.value,
                                        'status': mapped_status,
                                        'instance_spec': spec,
                                        'tags': tags_dict,
                                        'parent_resource_id': cluster_name,
                                        'last_synced_at': datetime.now(timezone.utc),
                                        'compute_mode': 'STANDARD',
                                        'scale_to_zero_eligible': True
                                    })
                                except ClientError as e:
                                    logger.warning(f"[EKSHandler] Error describing nodegroup {ng_name} in {cluster_name}: {e}")
                    except ClientError as e:
                        logger.warning(f"[EKSHandler] Error listing nodegroups for cluster {cluster_name}: {e}")
        except ClientError as e:
            # EKS might not be available or authorized in all regions
            logger.debug(f"[EKSHandler] Skipping region {region} due to error: {e}")
            
        return resources

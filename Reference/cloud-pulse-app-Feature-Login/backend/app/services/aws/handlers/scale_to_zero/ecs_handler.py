from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
import logging
import json
from botocore.exceptions import ClientError
from app.services.base_handler import BaseScaleToZeroHandler
from app.models.control.control_resource import ServiceType, ControlType
from app.services.aws.discovery.ecs_discovery import discover_asg_and_cp_status

logger = logging.getLogger(__name__)

class ECSScaleToZeroHandler(BaseScaleToZeroHandler):
    """
    Amazon ECS Plugin Handler.
    Supports Fargate (Serverless) and EC2-backed clusters.
    Implements Scale-to-Zero for ECS services and underlying unmanaged ASG capacity.
    """

    def _execute_get_state(self, session, native_id: str, **kwargs) -> str:
        # native_id is the service ARN: arn:aws:ecs:region:account:service/cluster-name/service-name
        cluster_name = native_id.split('/')[-2]
        service_name = native_id.split('/')[-1]
        
        ecs = session.client('ecs')
        res = ecs.describe_services(cluster=cluster_name, services=[service_name])
        services = res.get('services', [])
        
        if services:
            desired = services[0].get('desiredCount', 0)
            return 'RUNNING' if desired > 0 else 'STOPPED'
        return "UNKNOWN"

    def _execute_stop(self, session, native_id: str, **kwargs):
        region = kwargs.get('region')
        ecs = session.client('ecs')
        autoscaling = session.client('autoscaling')
        
        cluster_name = native_id.split('/')[-2]
        service_name = native_id.split('/')[-1]
        
        # 1. Get current ECS state
        res = ecs.describe_services(cluster=cluster_name, services=[service_name])
        services = res.get('services', [])
        if not services:
            raise Exception(f"ECS Service {service_name} not found in cluster {cluster_name}.")
            
        prev_ecs_desired = services[0].get('desiredCount', 0)
        
        # Zero-Lock Prevention
        if prev_ecs_desired == 0:
            prev_ecs_desired = 1
            
        # 2. Update ECS Service to 0
        ecs.update_service(cluster=cluster_name, service=service_name, desiredCount=0)
        
        # 3. Handle unmanaged ASG capacity (only if EC2 backed)
        has_managed_cp = False
        asg_name = None
        
        is_fargate = False
        if services[0].get('launchType') == 'FARGATE':
            is_fargate = True
        else:
            for cp in services[0].get('capacityProviderStrategy', []):
                if cp.get('capacityProvider', '').startswith('FARGATE'):
                    is_fargate = True
                    break
                    
        if not is_fargate:
            has_managed_cp, managed_asgs, unmanaged_asgs = discover_asg_and_cp_status(session, cluster_name, service_name, region=region)
        else:
            has_managed_cp, managed_asgs, unmanaged_asgs = False, [], []
        
        prev_asg_min = None
        prev_asg_desired = None
        asg_name = None
        
        target_asgs = unmanaged_asgs + managed_asgs
        
        peer_demand = 0
        if target_asgs:
            try:
                service = services[0]
                service_cps = [cp.get('capacityProvider') for cp in service.get('capacityProviderStrategy', []) if cp.get('capacityProvider')]
                
                paginator = ecs.get_paginator('list_services')
                for page in paginator.paginate(cluster=cluster_name):
                    service_arns = page.get('serviceArns', [])
                    if not service_arns:
                        continue
                    
                    peer_arns = [arn for arn in service_arns if arn.split('/')[-1] != service_name]
                    if not peer_arns:
                        continue
                        
                    for i in range(0, len(peer_arns), 10):
                        batch = peer_arns[i:i+10]
                        desc_res = ecs.describe_services(cluster=cluster_name, services=batch)
                        for peer_svc in desc_res.get('services', []):
                            is_daemon = peer_svc.get('schedulingStrategy') == 'DAEMON'
                            if is_daemon or peer_svc.get('desiredCount', 0) == 0:
                                continue
                            
                            peer_uses_same_compute = False
                            if service_cps:
                                peer_cps = [cp.get('capacityProvider') for cp in peer_svc.get('capacityProviderStrategy', []) if cp.get('capacityProvider')]
                                if set(service_cps).intersection(set(peer_cps)):
                                    peer_uses_same_compute = True
                            else:
                                peer_cps = [cp.get('capacityProvider') for cp in peer_svc.get('capacityProviderStrategy', []) if cp.get('capacityProvider')]
                                if not peer_cps:
                                    peer_uses_same_compute = True
                                    
                            if peer_uses_same_compute:
                                peer_demand += peer_svc.get('desiredCount', 0)
            except Exception as e:
                logger.warning(f"Error evaluating peer demand for cluster {cluster_name}: {e}")
        
        if target_asgs and peer_demand == 0:
            asg_name = target_asgs[0] # Just grab the first one for the config to restore later
            for a_name in target_asgs:
                asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[a_name])
                groups = asg_res.get('AutoScalingGroups', [])
                if groups:
                    # Save the state of the first one
                    if prev_asg_min is None:
                        prev_asg_min = groups[0].get('MinSize', 0)
                        prev_asg_desired = groups[0].get('DesiredCapacity', 0)
                    
                    # Scale ASG down
                    autoscaling.update_auto_scaling_group(
                        AutoScalingGroupName=a_name,
                        MinSize=0,
                        DesiredCapacity=0
                    )
                
        # 4. Serialize config
        config = {
            "cluster_name": cluster_name,
            "service_name": service_name,
            "has_managed_cp": has_managed_cp,
            "asg_name": asg_name,
            "prev_ecs_desired": prev_ecs_desired,
            "prev_asg_min": prev_asg_min,
            "prev_asg_desired": prev_asg_desired
        }
        
        return json.dumps(config)

    def _execute_start(self, session, native_id: str, saved_config: str, **kwargs):
        ecs = session.client('ecs')
        autoscaling = session.client('autoscaling')
        
        cluster_name = native_id.split('/')[-2]
        service_name = native_id.split('/')[-1]
        
        # Default fallback config
        config = {
            "cluster_name": cluster_name,
            "service_name": service_name,
            "has_managed_cp": False,
            "asg_name": None,
            "prev_ecs_desired": 1,
            "prev_asg_min": None,
            "prev_asg_desired": None
        }
        
        if saved_config:
            try:
                parsed_config = json.loads(saved_config)
                config.update(parsed_config)
            except Exception as e:
                logger.warning(f"Failed to parse saved config for ECS start, using fallbacks. Error: {e}")
                
        prev_ecs_desired = config.get('prev_ecs_desired', 1)
        
        # 1. Restore ASG first (if applicable)
        if config.get('asg_name'):
            asg_name = config.get('asg_name')
            prev_asg_min = config.get('prev_asg_min')
            prev_asg_desired = config.get('prev_asg_desired')
            
            if prev_asg_min is not None and prev_asg_desired is not None:
                try:
                    # We issue the ASG scale-up without blocking
                    # ECS will natively place tasks when instances join the cluster
                    autoscaling.update_auto_scaling_group(
                        AutoScalingGroupName=asg_name,
                        MinSize=prev_asg_min,
                        DesiredCapacity=prev_asg_desired
                    )
                except Exception as e:
                    logger.warning(f"Failed to restore ASG {asg_name} for ECS cluster {cluster_name}: {e}")
                    
        # 2. Restore ECS Service
        ecs.update_service(cluster=cluster_name, service=service_name, desiredCount=prev_ecs_desired)

    def _execute_scan_region(self, session, region: str) -> List[Dict[str, Any]]:
        from app.services.aws.discovery.ecs_discovery import discover_asg_and_cp_status
        resources = []
        cluster_asg_cache = {}

        ecs = session.client('ecs', region_name=region)
        try:
            cluster_paginator = ecs.get_paginator('list_clusters')
            for cluster_page in cluster_paginator.paginate():
                for cluster_arn in cluster_page.get('clusterArns', []):
                    cluster_name = cluster_arn.split('/')[-1]
                    
                    # Emit the standard ECS cluster as a parent resource so children can group under it
                    resources.append({
                        'resource_id': cluster_name,
                        'resource_name': cluster_name,
                        'cloud_provider': 'aws',
                        'region': region,
                        'service_type': ServiceType.ECS.value,
                        'control_type': ControlType.SCALE_TO_ZERO.value,
                        'status': 'ACTIVE',
                        'instance_spec': 'ECS Cluster',
                        'tags': {},
                        'parent_resource_id': None,
                        'last_synced_at': datetime.now(timezone.utc),
                        'compute_mode': 'STANDARD',
                        'scale_to_zero_eligible': False
                    })
                            
                    service_paginator = ecs.get_paginator('list_services')
                    for service_page in service_paginator.paginate(cluster=cluster_arn):
                        service_arns = service_page.get('serviceArns', [])
                        
                        if not service_arns:
                            continue
                            
                        for i in range(0, len(service_arns), 10):
                            batch = service_arns[i:i+10]
                            res = ecs.describe_services(cluster=cluster_arn, services=batch, include=['TAGS'])
                            for svc in res.get('services', []):
                                if svc.get('schedulingStrategy') == 'DAEMON':
                                    continue
                                    
                                svc_arn = svc.get('serviceArn')
                                svc_name = svc.get('serviceName')
                                desired = svc.get('desiredCount', 0)
                                status = 'RUNNING' if desired > 0 else 'STOPPED'
                                
                                is_fargate = False
                                if svc.get('launchType') == 'FARGATE':
                                    is_fargate = True
                                else:
                                    for cp in svc.get('capacityProviderStrategy', []):
                                        if cp.get('capacityProvider', '').startswith('FARGATE'):
                                            is_fargate = True
                                            break
                                            
                                asg_name = None
                                if not is_fargate:
                                    try:
                                        has_cp, managed, unmanaged = discover_asg_and_cp_status(session, cluster_name, svc_name, region=region)
                                        all_asgs = managed + unmanaged
                                        if all_asgs:
                                            asg_name = all_asgs[0]
                                    except Exception as e:
                                        logger.warning(f"Failed to discover ASG for {svc_name}: {e}")

                                if is_fargate:
                                    spec_type = "FARGATE"
                                elif asg_name:
                                    spec_type = f"ASG: {asg_name}"
                                else:
                                    spec_type = "EC2"
                                
                                tags_list = svc.get('tags', [])
                                tags_dict = {t.get('key'): t.get('value') for t in tags_list}
                                
                                resources.append({
                                    'resource_id': svc_arn,
                                    'resource_name': svc_name,
                                    'cloud_provider': 'aws',
                                    'region': region,
                                    'service_type': ServiceType.ECS.value,
                                    'control_type': ControlType.SCALE_TO_ZERO.value,
                                    'status': status,
                                    'instance_spec': f"{spec_type} | Tasks: {desired}",
                                    'tags': tags_dict,
                                    'parent_resource_id': cluster_name,
                                })
        except Exception as e:
            logger.error(f"Error scanning ECS in region {region}: {e}")
            
        return resources

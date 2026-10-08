from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def discover_asg_and_cp_status(session, cluster_name: str, service_name: str = None, region: str = None) -> Tuple[bool, list, list]:
    ecs = session.client('ecs', region_name=region) if region else session.client('ecs')
    ec2 = session.client('ec2', region_name=region) if region else session.client('ec2')
    
    has_managed_cp = False
    managed_asgs = []
    unmanaged_asgs = []
    
    target_cp_names = []
    # If service_name is provided, get its specific capacity providers
    if service_name:
        try:
            res = ecs.describe_services(cluster=cluster_name, services=[service_name])
            if res.get('services'):
                service = res['services'][0]
                target_cp_names = [cp.get('capacityProvider') for cp in service.get('capacityProviderStrategy', []) if cp.get('capacityProvider')]
        except Exception:
            pass
    
    # 1. Check Capacity Providers
    try:
        cluster_res = ecs.describe_clusters(clusters=[cluster_name])
        clusters = cluster_res.get('clusters', [])
        if clusters:
            if not target_cp_names:
                # Fallback to cluster default CPs if no service specific ones found
                target_cp_names = clusters[0].get('capacityProviders', [])
                
            if target_cp_names:
                cp_res = ecs.describe_capacity_providers(capacityProviders=target_cp_names)
                for cp in cp_res.get('capacityProviders', []):
                    asg_config = cp.get('autoScalingGroupProvider', {})
                    if asg_config.get('managedScaling', {}).get('status') == 'ENABLED':
                        has_managed_cp = True
                    
                    asg_arn = asg_config.get('autoScalingGroupArn')
                    if asg_arn:
                        asg_name = asg_arn.split('autoScalingGroupName/')[-1]
                        if asg_name not in managed_asgs:
                            managed_asgs.append(asg_name)
    except Exception as e:
        logger.warning(f"Error checking capacity providers for {cluster_name}: {e}")
        
    # 2. Inspect container instances to find ASG
    try:
        ci_arns = []
        if service_name:
            # Find tasks for this specific service
            next_token = None
            while True:
                kwargs = {'cluster': cluster_name, 'serviceName': service_name}
                if next_token:
                    kwargs['nextToken'] = next_token
                task_res = ecs.list_tasks(**kwargs)
                task_arns = task_res.get('taskArns', [])
                if task_arns:
                    desc_tasks = ecs.describe_tasks(cluster=cluster_name, tasks=task_arns[:100])
                    for task in desc_tasks.get('tasks', []):
                        ci_arn = task.get('containerInstanceArn')
                        if ci_arn and ci_arn not in ci_arns:
                            ci_arns.append(ci_arn)
                next_token = task_res.get('nextToken')
                if not next_token:
                    break
        
        if not ci_arns:
            next_token = None
            while True:
                kwargs = {'cluster': cluster_name, 'maxResults': 100}
                if next_token:
                    kwargs['nextToken'] = next_token
                ci_res = ecs.list_container_instances(**kwargs)
                ci_arns.extend(ci_res.get('containerInstanceArns', []))
                next_token = ci_res.get('nextToken')
                if not next_token:
                    break
            
        if ci_arns:
            desc_ci_res = ecs.describe_container_instances(cluster=cluster_name, containerInstances=ci_arns)
            instances = desc_ci_res.get('containerInstances', [])
            ec2_ids = [inst.get('ec2InstanceId') for inst in instances if inst.get('ec2InstanceId')]
            
            if ec2_ids:
                for i in range(0, len(ec2_ids), 100):
                    batch = ec2_ids[i:i+100]
                    ec2_res = ec2.describe_instances(InstanceIds=batch)
                    for resrv in ec2_res.get('Reservations', []):
                        for inst in resrv.get('Instances', []):
                            for tag in inst.get('Tags', []):
                                if tag.get('Key') == 'aws:autoscaling:groupName':
                                    asg_name = tag.get('Value')
                                    if asg_name not in unmanaged_asgs and asg_name not in managed_asgs:
                                        unmanaged_asgs.append(asg_name)
                                    break
    except Exception as e:
        logger.warning(f"Error discovering ASG for ECS cluster {cluster_name}: {e}")
        
    return has_managed_cp, managed_asgs, unmanaged_asgs


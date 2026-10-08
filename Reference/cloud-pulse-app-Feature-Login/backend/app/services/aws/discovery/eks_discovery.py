from typing import Tuple, List, Dict
import logging

logger = logging.getLogger(__name__)

def discover_eks_asgs_and_karpenter(session, cluster_name: str) -> Tuple[List[str], bool]:
    """
    Discovers unmanaged ASGs and Karpenter presence for a given EKS cluster.
    Returns: (unmanaged_asg_names, has_karpenter)
    """
    ec2 = session.client('ec2')
    autoscaling = session.client('autoscaling')
    
    unmanaged_asgs = []
    has_karpenter = False
    
    try:
        cluster_tag = f"kubernetes.io/cluster/{cluster_name}"
        
        # 1. Inspect EC2 instances for Karpenter and active Unmanaged ASGs
        paginator = ec2.get_paginator('describe_instances')
        for page in paginator.paginate(Filters=[
            {'Name': 'tag-key', 'Values': [cluster_tag]}
        ]):
            for resrv in page.get('Reservations', []):
                for inst in resrv.get('Instances', []):
                    tags = {t.get('Key'): t.get('Value') for t in inst.get('Tags', [])}
                    
                    if 'karpenter.sh/provisioner-name' in tags or 'karpenter.sh/nodepool' in tags:
                        has_karpenter = True
                    
                    asg_name = tags.get('aws:autoscaling:groupName')
                    is_managed = 'eks:nodegroup-name' in tags
                    
                    if asg_name and not is_managed and asg_name not in unmanaged_asgs:
                        unmanaged_asgs.append(asg_name)
                        
        # 2. Inspect ASGs directly to catch Scaled-to-Zero Unmanaged ASGs
        asg_paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
        from app.services.aws.discovery.asg_discovery import get_eks_cluster_from_asg_dict
        
        for page in asg_paginator.paginate():
            for asg in page.get('AutoScalingGroups', []):
                tags = {t['Key']: t['Value'] for t in asg.get('Tags', [])}
                is_managed = 'eks:nodegroup-name' in tags
                
                if not is_managed:
                    has_cluster_tag = cluster_tag in tags
                    
                    # If it has the tag natively on the ASG, it's ours
                    if has_cluster_tag:
                        asg_name = asg['AutoScalingGroupName']
                        if asg_name not in unmanaged_asgs:
                            unmanaged_asgs.append(asg_name)
                    # If it doesn't have the tag, but is scaled to zero, do deep inspection
                    elif asg['DesiredCapacity'] == 0:
                        deep_cluster = get_eks_cluster_from_asg_dict(asg, ec2)
                        if deep_cluster == cluster_name:
                            asg_name = asg['AutoScalingGroupName']
                            if asg_name not in unmanaged_asgs:
                                unmanaged_asgs.append(asg_name)
                        
    except Exception as e:
        logger.warning(f"Error discovering EC2/ASG resources for EKS cluster {cluster_name}: {e}")
        
    return unmanaged_asgs, has_karpenter

def map_all_eks_unmanaged_asgs(session, region: str) -> Dict[str, str]:
    """
    Returns a mapping of ASG Name -> EKS Cluster Name for all unmanaged EKS ASGs in the region.
    Inspects ASGs directly, and uses single-instance EC2 sampling for ASGs that only have tags on instances.
    """
    ec2 = session.client('ec2', region_name=region)
    autoscaling = session.client('autoscaling', region_name=region)
    asg_to_cluster = {}
    
    try:
        asg_paginator = autoscaling.get_paginator('describe_auto_scaling_groups')
        from app.services.aws.discovery.asg_discovery import get_eks_cluster_from_asg_dict
        
        for page in asg_paginator.paginate():
            for asg in page.get('AutoScalingGroups', []):
                tags = {t['Key']: t['Value'] for t in asg.get('Tags', [])}
                is_managed = 'eks:nodegroup-name' in tags
                
                if is_managed:
                    continue
                    
                asg_name = asg['AutoScalingGroupName']
                cluster_name = None
                
                # 1. Check ASG tags directly
                for k in tags.keys():
                    if k.startswith('kubernetes.io/cluster/'):
                        cluster_name = k.replace('kubernetes.io/cluster/', '')
                        break
                        
                if not cluster_name:
                    cluster_name = tags.get('aws:eks:cluster-name') or tags.get('eks:cluster-name')
                        
                if cluster_name:
                    asg_to_cluster[asg_name] = cluster_name
                    continue
                    
                # 2. If no ASG tags, check active EC2 instances (Sample the first instance)
                instances = asg.get('Instances', [])
                active_instances = [i['InstanceId'] for i in instances if i.get('LifecycleState') in ['InService', 'Pending']]
                
                if active_instances:
                    try:
                        inst_res = ec2.describe_instances(InstanceIds=[active_instances[0]])
                        for r in inst_res.get('Reservations', []):
                            for i in r.get('Instances', []):
                                i_tags = {t.get('Key'): t.get('Value') for t in i.get('Tags', [])}
                                for k in i_tags.keys():
                                    if k.startswith('kubernetes.io/cluster/'):
                                        cluster_name = k.replace('kubernetes.io/cluster/', '')
                                        break
                                if not cluster_name:
                                    cluster_name = i_tags.get('aws:eks:cluster-name') or i_tags.get('eks:cluster-name')
                    except Exception as e:
                        logger.debug(f"[EKS Map] Failed to describe instance {active_instances[0]} for ASG {asg_name}: {e}")
                        
                if cluster_name:
                    asg_to_cluster[asg_name] = cluster_name
                    continue
                    
                # 3. If no active instances (scaled to 0), do deep launch template inspection
                if asg['DesiredCapacity'] == 0:
                    deep_cluster = get_eks_cluster_from_asg_dict(asg, ec2)
                    if deep_cluster:
                        asg_to_cluster[asg_name] = deep_cluster
                        
    except Exception as e:
        logger.warning(f"Error mapping EKS ASGs in region {region}: {e}")
        
    return asg_to_cluster

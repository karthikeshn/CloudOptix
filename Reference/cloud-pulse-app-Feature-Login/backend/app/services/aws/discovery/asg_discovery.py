import re
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def find_parent_instance_from_asg(asg_name: str, autoscaling, ec2) -> str:
    """
    Auto-discovers the parent EC2 instance ID that an ASG was cloned from
    by traversing Launch Template -> AMI -> EBS Snapshot description.
    """
    try:
        
        # 1. Get ASG configuration
        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = asg_res.get('AutoScalingGroups', [])
        if not groups:
            return None
            
        asg = groups[0]
        
        # 2. Get Image ID from Launch Template OR Launch Configuration
        image_id = None
        
        if 'LaunchTemplate' in asg:
            lt = asg['LaunchTemplate']
            lt_id = lt.get('LaunchTemplateId')
            lt_version = lt.get('Version', '$Default')
            
            if lt_id:
                lt_res = ec2.describe_launch_template_versions(
                    LaunchTemplateId=lt_id,
                    Versions=[lt_version]
                )
                versions = lt_res.get('LaunchTemplateVersions', [])
                if versions:
                    image_id = versions[0].get('LaunchTemplateData', {}).get('ImageId')
                    
        elif 'LaunchConfigurationName' in asg:
            lc_name = asg['LaunchConfigurationName']
            lc_res = autoscaling.describe_launch_configurations(
                LaunchConfigurationNames=[lc_name]
            )
            lcs = lc_res.get('LaunchConfigurations', [])
            if lcs:
                image_id = lcs[0].get('ImageId')
                
        if not image_id:
            return None
            
        # 3. Get EBS Snapshot ID from AMI
        img_res = ec2.describe_images(ImageIds=[image_id])
        images = img_res.get('Images', [])
        if not images:
            return None
            
        block_devices = images[0].get('BlockDeviceMappings', [])
        snapshot_id = None
        for bd in block_devices:
            if 'Ebs' in bd and 'SnapshotId' in bd['Ebs']:
                snapshot_id = bd['Ebs']['SnapshotId']
                break
                
        if not snapshot_id:
            return None
            
        # 4. Get Snapshot Description and regex match instance ID
        snap_res = ec2.describe_snapshots(SnapshotIds=[snapshot_id])
        snapshots = snap_res.get('Snapshots', [])
        if not snapshots:
            return None
            
        desc = snapshots[0].get('Description', '')
        # Match standard AWS snapshot descriptions like "Created by CreateImage(...) for i-0abcd1234..."
        match = re.search(r'i-[a-f0-9]{8,17}', desc)
        if match:
            return match.group(0)
            
    except ClientError as e:
        logger.debug(f"[ASG Discovery] Failed to find parent for {asg_name}: {e}")
    except Exception as e:
        logger.debug(f"[ASG Discovery] Unexpected error for {asg_name}: {e}")
        
    return None

import base64

def get_ecs_cluster_from_launch_template(asg_name: str, autoscaling, ec2) -> str:
    """
    Parses the ASG's Launch Template UserData to find the ECS_CLUSTER environment variable.
    This is highly reliable for discovering ECS mapping for 0-capacity unmanaged ASGs.
    """
    import base64
    try:
        
        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = asg_res.get('AutoScalingGroups', [])
        if not groups:
            return None
        
        asg = groups[0]
        lt = asg.get('LaunchTemplate')
        if not lt:
            mip = asg.get('MixedInstancesPolicy', {})
            lt = mip.get('LaunchTemplate', {}).get('LaunchTemplateSpecification')
        
        if not lt:
            return None
            
        lt_id = lt.get('LaunchTemplateId')
        lt_version = lt.get('Version', '$Default')
        
        if not lt_id:
            return None
            
        lt_res = ec2.describe_launch_template_versions(
            LaunchTemplateId=lt_id,
            Versions=[lt_version]
        )
        versions = lt_res.get('LaunchTemplateVersions', [])
        if not versions:
            return None
            
        user_data_b64 = versions[0].get('LaunchTemplateData', {}).get('UserData')
        if not user_data_b64:
            return None
            
        user_data = base64.b64decode(user_data_b64).decode('utf-8')
        
        match = re.search(r'ECS_CLUSTER=([^\s"\']+)', user_data)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"[ASG Deep Inspection] Failed to inspect UserData for {asg_name}: {e}")
        
    return None

def get_eks_cluster_from_asg_dict(asg: dict, ec2_client) -> str:
    """
    Deep inspection of an ASG dictionary's Launch Template UserData to find EKS cluster name.
    Looks for /etc/eks/bootstrap.sh <cluster_name>
    """
    try:
        lt = asg.get('LaunchTemplate')
        if not lt:
            mip = asg.get('MixedInstancesPolicy', {})
            lt = mip.get('LaunchTemplate', {}).get('LaunchTemplateSpecification')
            
        if not lt:
            return None
            
        lt_id = lt.get('LaunchTemplateId')
        lt_version = lt.get('Version', '$Default')
        
        if not lt_id:
            return None
            
        lt_res = ec2_client.describe_launch_template_versions(
            LaunchTemplateId=lt_id,
            Versions=[lt_version]
        )
        versions = lt_res.get('LaunchTemplateVersions', [])
        if not versions:
            return None
            
        user_data_b64 = versions[0].get('LaunchTemplateData', {}).get('UserData')
        if not user_data_b64:
            return None
            
        user_data = base64.b64decode(user_data_b64).decode('utf-8')
        
        # Match standard EKS bootstrap: /etc/eks/bootstrap.sh [args...] <cluster-name>
        match = re.search(r'/etc/eks/bootstrap\.sh[^\n]*\s+([a-zA-Z0-9][a-zA-Z0-9-_]*)(?:\s|$)', user_data)
        if match:
            return match.group(1)
            
    except Exception as e:
        logger.debug(f"[ASG Deep Inspection] Failed to inspect UserData for EKS in ASG {asg.get('AutoScalingGroupName')}: {e}")
        
    return None

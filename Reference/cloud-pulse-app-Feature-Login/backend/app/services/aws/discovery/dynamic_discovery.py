import logging
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.control.control_resource import ControlResource, ServiceType, ControlType
from app.models.control.control_action_log import ControlActionLog
from app.services.action_logger import log_control_action
from app.models.system.system_notification import SystemNotification

logger = logging.getLogger(__name__)

async def discover_and_upsert_child_ec2(
    session: AsyncSession,
    aws_session,
    account_name: str,
    region: str,
    parent_service_type: str,
    parent_resource_id: str
):
    try:
        autoscaling = aws_session.client('autoscaling', region_name=region)
        ec2 = aws_session.client('ec2', region_name=region)
        ecs = aws_session.client('ecs', region_name=region)
        
        asg_name = None
        
        if parent_service_type.upper() == 'ASG':
            asg_name = parent_resource_id.split('/')[-1]
            
        elif parent_service_type.upper() == 'ECS':
            parts = parent_resource_id.split('/')
            if len(parts) >= 2:
                cluster_name = parts[-2]
                service_name = parts[-1]
                try:
                    res = ecs.describe_services(cluster=cluster_name, services=[service_name])
                    if res.get('services'):
                        cps = res['services'][0].get('capacityProviderStrategy', [])
                        for cp in cps:
                            cp_name = cp.get('capacityProvider')
                            if cp_name:
                                cp_res = ecs.describe_capacity_providers(capacityProviders=[cp_name])
                                for c in cp_res.get('capacityProviders', []):
                                    asg_arn = c.get('autoScalingGroupProvider', {}).get('autoScalingGroupArn')
                                    if asg_arn:
                                        asg_name = asg_arn.split('/')[-1]
                                        break
                            if asg_name:
                                break
                except Exception as e:
                    logger.warning(f"[Discovery] Failed to resolve ASG from ECS: {e}")
        
        if not asg_name:
            logger.info(f"[Discovery] No ASG found for {parent_service_type} {parent_resource_id}")
            return
            
        # 1. Get ASG Instances
        asg_res = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        groups = asg_res.get('AutoScalingGroups', [])
        
        instance_ids = []
        if groups:
            instance_ids = [inst['InstanceId'] for inst in groups[0].get('Instances', [])]
            
        # 1.5 Garbage collect stale child EC2 instances
        stmt = select(ControlResource).where(
            ControlResource.parent_resource_id == parent_resource_id,
            ControlResource.service_type == ServiceType.EC2
        )
        existing_children = (await session.execute(stmt)).scalars().all()
        for child in existing_children:
            if child.resource_id not in instance_ids:
                await session.delete(child)
                logger.info(f"[Discovery] Garbage collected stale child EC2: {child.resource_id}")
                
        if not instance_ids:
            await session.commit()
            return
            
        # 2. Get EC2 details
        ec2_res = ec2.describe_instances(InstanceIds=instance_ids)
        for reservation in ec2_res.get('Reservations', []):
            for inst in reservation.get('Instances', []):
                inst_id = inst['InstanceId']
                state = inst['State']['Name'].upper()
                
                tags_json = {t['Key']: t['Value'] for t in inst.get('Tags', [])}
                name = tags_json.get('Name', inst_id)
                
                stmt = select(ControlResource).where(ControlResource.resource_id == inst_id)
                result = await session.execute(stmt)
                db_res = result.scalars().first()
                
                if db_res:
                    db_res.status = state
                    db_res.parent_resource_id = parent_resource_id
                else:
                    # Inherit visibility from parent if possible
                    is_visible = True
                    if parent_resource_id:
                        parent_stmt = select(ControlResource).where(ControlResource.resource_id == parent_resource_id)
                        parent_result = await session.execute(parent_stmt)
                        parent_res = parent_result.scalars().first()
                        if parent_res:
                            is_visible = parent_res.is_visible

                    new_res = ControlResource(
                        resource_id=inst_id,
                        resource_name=name,
                        cloud_provider="aws",
                        account_name=account_name,
                        region=region,
                        service_type=ServiceType.EC2,
                        control_type=ControlType.SCALE_TO_ZERO,
                        status=state,
                        parent_resource_id=parent_resource_id,
                        is_automation_enabled=False,
                        is_visible=is_visible,
                        tags_json=json.dumps(tags_json)
                    )
                    session.add(new_res)
                    
                    # Log the dynamic discovery
                    log_control_action(
                        session=session,
                        native_id=inst_id,
                        account_name=account_name,
                        provider="aws",
                        action_type="DISCOVERED",
                        status="SUCCESS",
                        details=f"Child resource dynamically discovered via {parent_service_type} scaling.",
                        resource_name=name,
                        resource_type=new_res.service_type.value
                    )
                    
                    notification = SystemNotification(
                        title="New Resource Discovered",
                        message=f"{name} ({inst_id}) was dynamically discovered via {parent_service_type} scaling.",
                        type="INFO",
                        module="CONTROL"
                    )
                    session.add(notification)
                    
        await session.commit()
        logger.info(f"[Discovery] Upserted {len(instance_ids)} EC2 instances for parent {parent_resource_id}")
        
    except Exception as e:
        logger.error(f"[Discovery] Targeted discovery failed: {e}")

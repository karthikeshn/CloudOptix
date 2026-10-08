from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text, func, case, and_, or_
from typing import Optional
from app.models import ControlResource, ConfigCloudAccount

class ControlRepository:
    
    @staticmethod
    async def get_all_schedules(db: AsyncSession):
        stmt = select(ControlResource).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(ConfigCloudAccount.active_modules.like("%control%")).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(ConfigCloudAccount.active_modules.like("%control%"))
        res = await db.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def get_dashboard_summary(db: AsyncSession, account_name: Optional[str] = None, provider: Optional[str] = None, region: Optional[str] = None, tag: Optional[str] = None, service_type: Optional[str] = None, status: Optional[str] = None):
        conditions = [ControlResource.is_visible == True]
        
        # DYNAMIC: Exclude ONLY non-actionable parent clusters (like ECS Clusters, Beanstalk Apps) from the count.
        # Actionable parents like ASGs and Beanstalk Environments (which can be STOPPED/RUNNING) should be counted.
        # We identify non-actionable parents as those with a status of 'ACTIVE' or 'UNKNOWN'.
        parent_ids_stmt = select(ControlResource.parent_resource_id).where(ControlResource.parent_resource_id.is_not(None)).distinct()
        parent_ids_res = await db.execute(parent_ids_stmt)
        parent_ids = [pid for pid in parent_ids_res.scalars().all() if pid]
        
        if parent_ids:
            conditions.append(
                ~and_(
                    ControlResource.resource_id.in_(parent_ids),
                    ControlResource.status.in_(['ACTIVE', 'UNKNOWN'])
                )
            )
        
        if account_name and account_name != 'All Accounts':
            conditions.append(ControlResource.account_name == account_name)
        if provider and provider != 'AWS':
            conditions.append(ControlResource.cloud_provider == provider.lower())
        if region and region != 'All Regions':
            conditions.append(ControlResource.region == region)
        if tag and tag != 'All Tags':
            tag_key = tag.split(":")[0]
            conditions.append(ControlResource.tags_json.like(f'%"{tag_key}"%'))
        if status and status != 'All':
            conditions.append(ControlResource.status == status)
        if service_type:
            types = [t.strip() for t in service_type.split(',')]
            if len(types) == 1:
                conditions.append(ControlResource.service_type == types[0])
            else:
                conditions.append(ControlResource.service_type.in_(types))
            
        stmt = select(
            func.count(ControlResource.resource_id),
            func.sum(case((ControlResource.status == 'RUNNING', 1), else_=0)),
            func.sum(case((ControlResource.status == 'STOPPED', 1), else_=0)),
            func.sum(case((ControlResource.status == 'TERMINATED', 1), else_=0)),
            func.sum(case((ControlResource.is_automation_enabled == True, 1), else_=0))
        ).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(and_(*conditions) if conditions else True).where(ConfigCloudAccount.active_modules.like("%control%"))
            
        res = await db.execute(stmt)
        row = res.first()
        
        type_stmt = select(ControlResource.service_type, func.count()).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(and_(*conditions) if conditions else True).where(ConfigCloudAccount.active_modules.like("%control%")).group_by(ControlResource.service_type)
        type_res = await db.execute(type_stmt)
        type_breakdown = [{"type": t, "count": c} for t, c in type_res.all()]
        type_breakdown.sort(key=lambda x: x["count"], reverse=True)
        
        reg_stmt = select(ControlResource.region, func.count()).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(and_(*conditions) if conditions else True).where(ConfigCloudAccount.active_modules.like("%control%")).group_by(ControlResource.region)
        reg_res = await db.execute(reg_stmt)
        region_breakdown = [{"region": r, "count": c} for r, c in reg_res.all() if r]
        
        return {
            "total_count": int(row[0] or 0),
            "running_count": int(row[1] or 0),
            "stopped_count": int(row[2] or 0),
            "terminated_count": int(row[3] or 0),
            "active_schedules_count": int(row[4] or 0),
            "type_breakdown": type_breakdown,
            "region_breakdown": region_breakdown
        }

    @staticmethod
    async def get_filtered_resources(db: AsyncSession, limit: int, offset: int, show_hidden: bool, account_name: Optional[str] = None, provider: Optional[str] = None, region: Optional[str] = None, tag: Optional[str] = None):
        stmt = select(ControlResource).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(ConfigCloudAccount.active_modules.like("%control%"))
        
        if not show_hidden:
            stmt = stmt.where(ControlResource.is_visible == True)
            
        if account_name and account_name != 'All Accounts':
            stmt = stmt.where(ControlResource.account_name == account_name)
        if provider and provider != 'AWS': # Default if empty or 'AWS' for now
            stmt = stmt.where(ControlResource.cloud_provider == provider.lower())
        if region and region != 'All Regions':
            stmt = stmt.where(ControlResource.region == region)
        if tag and tag != 'All Tags':
            tag_key = tag.split(":")[0]
            stmt = stmt.where(ControlResource.tags_json.like(f'%"{tag_key}"%'))
            
        stmt = stmt.limit(limit).offset(offset)
            
        res = await db.execute(stmt)
        schedules = list(res.scalars().all())
        
        if not schedules:
            return []
            
        # Eager-load families to fix frontend Group View during pagination
        parent_ids = {s.parent_resource_id for s in schedules if s.parent_resource_id}
        resource_ids = {s.resource_id for s in schedules}
        missing_parents = parent_ids - resource_ids
        
        all_parent_ids = resource_ids.union(missing_parents)
        
        if missing_parents:
            parent_stmt = select(ControlResource).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(ConfigCloudAccount.active_modules.like("%control%")).where(ControlResource.resource_id.in_(missing_parents))
            parent_res = await db.execute(parent_stmt)
            schedules.extend(parent_res.scalars().all())
            
        if all_parent_ids:
            child_stmt = select(ControlResource).join(ConfigCloudAccount, ControlResource.account_name == ConfigCloudAccount.account_name).where(ConfigCloudAccount.active_modules.like("%control%")).where(ControlResource.parent_resource_id.in_(all_parent_ids))
            if not show_hidden:
                child_stmt = child_stmt.where(ControlResource.is_visible == True)
                
            child_res = await db.execute(child_stmt)
            children = child_res.scalars().all()
            
            existing_ids = {s.resource_id for s in schedules}
            for child in children:
                if child.resource_id not in existing_ids:
                    schedules.append(child)
                    existing_ids.add(child.resource_id)
                    
        return schedules

    @staticmethod
    async def update_visibility(db: AsyncSession, resource_ids: list[str], is_visible: bool):
        # Base case: update the explicitly provided IDs
        all_ids_to_update = set(resource_ids)
        
        # Recursively find all children to cascade the visibility toggle
        current_parent_ids = list(resource_ids)
        while current_parent_ids:
            # Find children of the current parents
            child_stmt = select(ControlResource.resource_id).where(ControlResource.parent_resource_id.in_(current_parent_ids))
            child_res = await db.execute(child_stmt)
            child_ids = child_res.scalars().all()
            
            if not child_ids:
                break
                
            all_ids_to_update.update(child_ids)
            current_parent_ids = child_ids

        stmt = (
            update(ControlResource)
            .where(ControlResource.resource_id.in_(all_ids_to_update))
            .values(is_visible=is_visible)
        )
        await db.execute(stmt)
        await db.commit()
        return len(all_ids_to_update)

    @staticmethod
    async def get_filter_options(db: AsyncSession, account_name: Optional[str] = None, provider: Optional[str] = None):
        where_clause = "1=1"
        params = {}
        
        if account_name and account_name != 'All Accounts':
            where_clause += " AND r.account_name = :account"
            params['account'] = account_name
        if provider:
            where_clause += " AND r.cloud_provider = :provider"
            params['provider'] = provider.lower()

        # 1. Distinct Regions
        region_stmt = text(f"""
            SELECT DISTINCT r.region 
            FROM control_resources r
            JOIN config_cloud_accounts c ON r.account_name = c.account_name
            WHERE {where_clause} AND r.region IS NOT NULL AND r.region != ''
            AND c.active_modules LIKE '%control%'
        """)
        regions = [r[0] for r in (await db.execute(region_stmt, params)).all()]

        # 2. Distinct Tags using SQLite JSON extraction
        tags_stmt = text(f"""
            SELECT DISTINCT j.key 
            FROM control_resources r
            JOIN config_cloud_accounts c ON r.account_name = c.account_name,
            json_each(r.tags_json) j
            WHERE {where_clause} AND r.tags_json IS NOT NULL AND r.tags_json != '{{}}'
            AND c.active_modules LIKE '%control%'
        """)
        tags = [r[0] for r in (await db.execute(tags_stmt, params)).all()]
                
        return {
            "regions": sorted(regions),
            "tags": sorted(tags)
        }

control_repository = ControlRepository()

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, or_, delete
from app.models import InventoryResource, InventoryChange, InventorySnapshot
from datetime import datetime, timedelta
import json

class InventoryRepository:
    
    @staticmethod
    async def get_summary(db: AsyncSession, account: str = None) -> dict:
        conditions = [InventoryResource.status == "active"]
        if account: conditions.append(InventoryResource.account_name == account)
        stmt = select(InventoryResource).where(and_(*conditions))
        result = await db.execute(stmt)
        active_items = result.scalars().all()
        
        total = len(active_items)
        billable = sum(1 for x in active_items if x.billable)
        non_billable = total - billable
        
        today_prefix = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
        new_today = sum(1 for x in active_items if x.first_seen_date and x.first_seen_date.startswith(today_prefix))
        
        del_conditions = [InventoryResource.status == "deleted", InventoryResource.deleted_at.like(f"{today_prefix}%")]
        if account: del_conditions.append(InventoryResource.account_name == account)
        del_stmt = select(InventoryResource).where(and_(*del_conditions))
        del_result = await db.execute(del_stmt)
        deleted_today = len(del_result.scalars().all())
        
        by_type = {}
        by_region = {}
        for x in active_items:
            by_type[x.resource_type] = by_type.get(x.resource_type, 0) + 1
            by_region[x.region] = by_region.get(x.region, 0) + 1
            
        return {
            "total_active": total,
            "billable": billable,
            "non_billable": non_billable,
            "new_today": new_today,
            "deleted_today": deleted_today,
            "by_type": by_type,
            "by_region": by_region
        }
        
    @staticmethod
    async def wipe_database(db: AsyncSession, provider: str = None, account: str = None):
        if account and provider:
            await db.execute(delete(InventoryResource).where(and_(InventoryResource.account_name == account, InventoryResource.provider == provider.lower())))
            await db.execute(delete(InventoryChange).where(InventoryChange.account_name == account))
            await db.execute(delete(InventorySnapshot).where(InventorySnapshot.account_name == account))
        elif account:
            await db.execute(delete(InventoryResource).where(InventoryResource.account_name == account))
            await db.execute(delete(InventoryChange).where(InventoryChange.account_name == account))
            await db.execute(delete(InventorySnapshot).where(InventorySnapshot.account_name == account))
        else:
            await db.execute(delete(InventoryResource))
            await db.execute(delete(InventoryChange))
            await db.execute(delete(InventorySnapshot))
        await db.commit()

    @staticmethod
    async def get_changes(
        db: AsyncSession, account: str = None, days: int = 30, change_type: str = None,
        search: str = None, region: str = None, linked_account: str = None, tag: str = None,
        limit: int = 50, offset: int = 0
    ) -> dict:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        conditions = [InventoryChange.timestamp >= cutoff_date]
        if account: conditions.append(InventoryChange.account_name == account)
        
        if change_type and change_type != 'All':
            conditions.append(InventoryChange.change_type == change_type)
            
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    InventoryChange.native_id.ilike(search_term),
                    InventoryResource.resource_type.ilike(search_term),
                    InventoryResource.name.ilike(search_term)
                )
            )
            
        if region and region != 'All Regions':
            conditions.append(InventoryResource.region == region)
        if linked_account and linked_account != 'All Accounts':
            conditions.append(InventoryResource.linked_account == linked_account)
        if tag and tag != 'All':
            conditions.append(InventoryResource.tags.like(f'%"{tag}"%'))
            
        count_stmt = select(func.count(InventoryChange.id)).outerjoin(
            InventoryResource, 
            and_(InventoryChange.native_id == InventoryResource.native_id, InventoryChange.account_name == InventoryResource.account_name)
        ).where(and_(*conditions))
        total_count = (await db.execute(count_stmt)).scalar() or 0
        
        stmt = select(InventoryChange, InventoryResource).outerjoin(
            InventoryResource, 
            and_(InventoryChange.native_id == InventoryResource.native_id, InventoryChange.account_name == InventoryResource.account_name)
        ).where(and_(*conditions)).order_by(InventoryChange.timestamp.desc()).limit(limit).offset(offset)
        
        result = await db.execute(stmt)
        rows = result.all()
        
        return {
            "total": total_count,
            "page": (offset // limit) + 1 if limit > 0 else 1,
            "changes": [
                {
                    "id": row.InventoryChange.id,
                    "native_id": row.InventoryChange.native_id,
                    "change_type": row.InventoryChange.change_type,
                    "detected_at": row.InventoryChange.timestamp,
                    "details": json.loads(row.InventoryChange.details) if getattr(row.InventoryChange, 'details', None) else None,
                    "resource_type": row.InventoryResource.resource_type if row.InventoryResource else "Unknown",
                    "region": row.InventoryResource.region if row.InventoryResource else "Unknown",
                    "name": row.InventoryResource.name if row.InventoryResource else None
                }
                for row in rows
            ]
        }

    @staticmethod
    async def get_trend(db: AsyncSession, account: str = None, resource_type: str = None, days: int = 30):
        conditions = []
        if account: conditions.append(InventorySnapshot.account_name == account)
        
        if days:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            conditions.append(InventorySnapshot.snapshot_date >= cutoff_date)

        stmt = select(InventorySnapshot).where(and_(*conditions) if conditions else True).order_by(InventorySnapshot.snapshot_date.asc())
        result = await db.execute(stmt)
        snapshots = result.scalars().all()
        
        return [
            {
                "id": s.id,
                "snapshot_date": s.snapshot_date,
                "total_active_count": json.loads(s.category_breakdown).get(resource_type, 0) if resource_type and s.category_breakdown else s.total_active_count,
                "billable_count": s.billable_count,
                "non_billable_count": s.non_billable_count,
                "deleted_today": s.deleted_today,
                "category_breakdown": json.loads(s.category_breakdown) if s.category_breakdown else {}
            }
            for s in snapshots
        ]

    @staticmethod
    async def get_filter_options(db: AsyncSession, account: str = None, provider: str = None):
        from sqlalchemy import text
        where_clause = "status = 'active'"
        params = {}
        
        if account:
            where_clause += " AND account_name = :account"
            params['account'] = account
        if provider:
            where_clause += " AND provider = :provider"
            params['provider'] = provider

        region_stmt = text(f"SELECT DISTINCT region FROM inventory_resources WHERE {where_clause} AND region IS NOT NULL AND region != ''")
        regions = [r[0] for r in (await db.execute(region_stmt, params)).all()]

        linked_stmt = text(f"SELECT DISTINCT linked_account FROM inventory_resources WHERE {where_clause} AND linked_account IS NOT NULL AND linked_account != 'Unknown' AND linked_account != ''")
        linked = [l[0] for l in (await db.execute(linked_stmt, params)).all()]

        tags_stmt = text(f"""
            SELECT DISTINCT j.key 
            FROM inventory_resources r, json_each(r.tags) j
            WHERE {where_clause} 
            AND json_valid(r.tags) = 1
        """)
        tags = [t[0] for t in (await db.execute(tags_stmt, params)).all() if t[0]]

        return {
            "regions": sorted(regions),
            "linked_accounts": sorted(linked),
            "tags": sorted(tags)
        }

    @staticmethod
    async def get_activity_heatmap(db: AsyncSession, account: str = None, resource_type: str = None):
        cutoff_date = datetime.utcnow() - timedelta(days=180)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        stmt = select(InventoryResource)
        if account:
            stmt = stmt.where(InventoryResource.account_name == account)
        if resource_type:
            stmt = stmt.where(InventoryResource.resource_type == resource_type)
        
        result = await db.execute(stmt)
        resources = result.scalars().all()
        
        activity = {}
        for r in resources:
            if r.first_seen_date and len(r.first_seen_date) >= 10:
                d = r.first_seen_date[:10]
                if d >= cutoff_str:
                    if d not in activity: activity[d] = {"created": 0, "deleted": 0, "updated": 0}
                    activity[d]["created"] += 1
            if r.deleted_at and len(r.deleted_at) >= 10:
                d = r.deleted_at[:10]
                if d >= cutoff_str:
                    if d not in activity: activity[d] = {"created": 0, "deleted": 0, "updated": 0}
                    activity[d]["deleted"] += 1
                    
        change_stmt = select(InventoryChange.timestamp).where(InventoryChange.change_type == 'updated', InventoryChange.timestamp >= cutoff_date)
        if account:
            change_stmt = change_stmt.where(InventoryChange.account_name == account)
        if resource_type:
            change_stmt = change_stmt.join(InventoryResource, and_(InventoryChange.native_id == InventoryResource.native_id, InventoryChange.account_name == InventoryResource.account_name)).where(InventoryResource.resource_type == resource_type)
            
        change_result = await db.execute(change_stmt)
        updates = change_result.scalars().all()
        for ts in updates:
            d = ts.strftime("%Y-%m-%d")
            if d not in activity: activity[d] = {"created": 0, "deleted": 0, "updated": 0}
            activity[d]["updated"] += 1
                
        heatmap_data = [
            {
                "date": k, 
                "count": v["created"] + v["deleted"] + v.get("updated", 0),
                "created": v["created"],
                "deleted": v["deleted"],
                "updated": v.get("updated", 0)
            } 
            for k, v in sorted(activity.items())
        ]
        return heatmap_data

    @staticmethod
    async def get_advanced_summary(db: AsyncSession, account: str, provider: str = None, region: str = None, linked_account: str = None, tag: str = None, resource_type: str = None) -> dict:
        conditions = [InventoryResource.status == "active"]
        if account: conditions.append(InventoryResource.account_name == account)
        if provider: conditions.append(InventoryResource.provider == provider)
        if region and region != 'All Regions': conditions.append(InventoryResource.region == region)
        if linked_account and linked_account != 'All Accounts': conditions.append(InventoryResource.linked_account == linked_account)
        if tag and tag != 'All': conditions.append(InventoryResource.tags.like(f'%"{tag}"%'))
        if resource_type:
            types = [t.strip() for t in resource_type.split(',')]
            if len(types) == 1:
                conditions.append(InventoryResource.resource_type == types[0])
            else:
                conditions.append(InventoryResource.resource_type.in_(types))
        
        from sqlalchemy import case
        today_prefix = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
        
        summary_stmt = select(
            func.count(),
            func.sum(case((InventoryResource.billable == True, 1), else_=0)),
            func.sum(case((InventoryResource.first_seen_date.like(f"{today_prefix}%"), 1), else_=0)),
            func.sum(case(((InventoryResource.tags == None) | (InventoryResource.tags == "") | (InventoryResource.tags == "{}"), 1), else_=0))
        ).where(and_(*conditions))
        
        row = (await db.execute(summary_stmt)).first()
        total = row[0] or 0
        billable = row[1] or 0
        new_today = row[2] or 0
        untagged = row[3] or 0
        non_billable = total - billable
        tagged = total - untagged
        
        del_conds = [InventoryResource.status == "deleted", InventoryResource.deleted_at.like(f"{today_prefix}%")]
        if account: del_conds.append(InventoryResource.account_name == account)
        if provider: del_conds.append(InventoryResource.provider == provider)
        if region and region != 'All Regions': del_conds.append(InventoryResource.region == region)
        if linked_account and linked_account != 'All Accounts': del_conds.append(InventoryResource.linked_account == linked_account)
        if tag and tag != 'All': del_conds.append(InventoryResource.tags.like(f'%"{tag}"%'))
        if resource_type:
            types = [t.strip() for t in resource_type.split(',')]
            if len(types) == 1:
                del_conds.append(InventoryResource.resource_type == types[0])
            else:
                del_conds.append(InventoryResource.resource_type.in_(types))
        
        deleted_today_stmt = select(func.count()).where(and_(*del_conds))
        deleted_today = (await db.execute(deleted_today_stmt)).scalar() or 0
        
        del_type_conds = [InventoryResource.status == "deleted"]
        if account: del_type_conds.append(InventoryResource.account_name == account)
        if provider: del_type_conds.append(InventoryResource.provider == provider)
        if region and region != 'All Regions': del_type_conds.append(InventoryResource.region == region)
        if linked_account and linked_account != 'All Accounts': del_type_conds.append(InventoryResource.linked_account == linked_account)
        if tag and tag != 'All': del_type_conds.append(InventoryResource.tags.like(f'%"{tag}"%'))
        if resource_type:
            types = [t.strip() for t in resource_type.split(',')]
            if len(types) == 1:
                del_type_conds.append(InventoryResource.resource_type == types[0])
            else:
                del_type_conds.append(InventoryResource.resource_type.in_(types))
        
        del_type_stmt = select(InventoryResource.resource_type, func.count()).where(and_(*del_type_conds)).group_by(InventoryResource.resource_type)
        del_type_res = await db.execute(del_type_stmt)
        deleted_type_breakdown = [{"type": t, "count": c} for t, c in del_type_res.all()]
        deleted_type_breakdown.sort(key=lambda x: x["count"], reverse=True)
        
        del_reg_stmt = select(InventoryResource.region, func.count()).where(and_(*del_type_conds)).group_by(InventoryResource.region)
        del_reg_res = await db.execute(del_reg_stmt)
        deleted_region_breakdown = [{"region": r, "count": c} for r, c in del_reg_res.all() if r]
        
        type_stmt = select(InventoryResource.resource_type, func.count()).where(and_(*conditions)).group_by(InventoryResource.resource_type)
        type_res = await db.execute(type_stmt)
        type_breakdown = [{"type": t, "count": c} for t, c in type_res.all()]
        type_breakdown.sort(key=lambda x: x["count"], reverse=True)
        
        reg_stmt = select(InventoryResource.region, func.count()).where(and_(*conditions)).group_by(InventoryResource.region)
        reg_res = await db.execute(reg_stmt)
        region_breakdown = [{"region": r, "count": c} for r, c in reg_res.all() if r]
        
        link_stmt = select(InventoryResource.linked_account, func.count()).where(and_(*conditions)).group_by(InventoryResource.linked_account)
        link_res = await db.execute(link_stmt)
        linked_breakdown = [{"linked_account": r, "count": c} for r, c in link_res.all() if r and r != 'Unknown']
        
        return {
            "total": total,
            "billable": billable,
            "non_billable": non_billable,
            "new_today": new_today,
            "deleted_today": deleted_today,
            "tagged": tagged,
            "untagged": untagged,
            "type_breakdown": type_breakdown,
            "deleted_type_breakdown": deleted_type_breakdown,
            "region_breakdown": region_breakdown,
            "deleted_region_breakdown": deleted_region_breakdown,
            "linked_breakdown": linked_breakdown,
            "group_breakdown": type_breakdown
        }

    @staticmethod
    async def get_paginated_resources(
        db: AsyncSession, 
        account: str = None, 
        provider: str = None,
        resource_type: str = None,
        region: str = None,
        billable: bool = None,
        linked_account: str = None,
        tag: str = None,
        time_filter: str = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0
    ) -> dict:
        conditions = [InventoryResource.status == status]
        if account: conditions.append(InventoryResource.account_name == account)
        if provider: conditions.append(InventoryResource.provider == provider)
        if resource_type:
            types = [t.strip() for t in resource_type.split(',')]
            if len(types) == 1:
                conditions.append(InventoryResource.resource_type == types[0])
            else:
                conditions.append(InventoryResource.resource_type.in_(types))
        if region and region != 'All Regions': conditions.append(InventoryResource.region == region)
        if linked_account and linked_account != 'All Accounts': conditions.append(InventoryResource.linked_account == linked_account)
        if tag and tag != 'All': conditions.append(InventoryResource.tags.like(f'%"{tag}"%'))
        if billable is not None: conditions.append(InventoryResource.billable == billable)
        
        if time_filter == 'Today':
            today_prefix = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
            if status == 'deleted':
                conditions.append(InventoryResource.deleted_at.like(f"{today_prefix}%"))
            else:
                conditions.append(InventoryResource.first_seen_date.like(f"{today_prefix}%"))
        
        count_stmt = select(func.count()).where(and_(*conditions))
        total_count = (await db.execute(count_stmt)).scalar() or 0
        
        stmt = select(InventoryResource).where(and_(*conditions)).limit(limit).offset(offset)
        result = await db.execute(stmt)
        resources = result.scalars().all()
        
        response = {
            "total": total_count,
            "page": (offset // limit) + 1 if limit > 0 else 1,
            "resources": [
                {
                    "id": r.id,
                    "native_id": r.native_id,
                    "name": r.name,
                    "tags": r.tags,
                    "resource_type": r.resource_type,
                    "provider": r.provider,
                    "account_name": r.account_name,
                    "linked_account": r.linked_account,
                    "region": r.region,
                    "billable": r.billable,
                    "status": r.status,
                    "first_seen_date": r.first_seen_date,
                    "deleted_at": r.deleted_at
                }
                for r in resources
            ]
        }

        if offset == 0:
            reg_stmt = select(InventoryResource.region, func.count()).where(and_(*conditions)).group_by(InventoryResource.region)
            reg_res = await db.execute(reg_stmt)
            response["region_breakdown"] = [{"region": r, "count": c} for r, c in reg_res.all() if r]

            type_stmt = select(InventoryResource.resource_type, func.count()).where(and_(*conditions)).group_by(InventoryResource.resource_type)
            type_res = await db.execute(type_stmt)
            response["type_breakdown"] = [{"type": t, "count": c} for t, c in type_res.all()]
            
        return response

inventory_repository = InventoryRepository()

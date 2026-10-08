import asyncio
import concurrent.futures
from datetime import datetime
import time
import os
import logging
from typing import List, Dict, Any, Optional

from app.services.aws.session import AWSSessionManager
from app.services.aws.handlers import REGISTERED_HANDLERS

logger = logging.getLogger(__name__)

# Using max_workers=20 is the sweet spot. 
# Increasing this causes AWS API Throttling (RequestLimitExceeded), leading to exponential backoffs (sleeps) that actually make the scan slower.
_SCANNER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=20)

HANDLER_SERVICE_MAP = {
    'EC2Handler': 'ec2',
    'RDSHandler': 'rds',
    'DocumentDBHandler': 'docdb',
    'RedshiftHandler': 'redshift',
    'SageMakerHandler': 'sagemaker',
    'WorkSpacesHandler': 'workspaces',
    'ASGHandler': 'autoscaling',
    'ECSScaleToZeroHandler': 'ecs',
    'EKSHandler': 'eks',
    'AppRunnerHandler': 'apprunner',
    'BeanstalkHandler': 'elasticbeanstalk'
}

class AWSParallelScanner:
    """
    High-performance multi-threaded scanner for AWS infrastructure.
    Uses dynamic Strategy Pattern plugins (Handlers) to scan all registered services across active regions concurrently.
    """
    def __init__(self, session_manager: Optional[AWSSessionManager] = None):
        self.session_manager = session_manager or AWSSessionManager()
        self.handlers = REGISTERED_HANDLERS

    def get_active_regions(self, credentials: dict, default_region: str = "us-east-1") -> List[str]:
        try:
            session = self.session_manager.create_session(credentials, default_region)
            ec2_client = session.client('ec2', region_name=default_region)
            res = ec2_client.describe_regions()
            regions = [r['RegionName'] for r in res.get('Regions', []) if r.get('OptInStatus') in ('opt-in-not-required', 'opted-in', None)]
            return regions if regions else [default_region]
        except Exception as e:
            logger.warning(f"[AWS Scanner] Failed to describe regions, falling back to default region '{default_region}': {e}")
            return [default_region]

    async def scan_all_resources_parallel(self, credentials: dict, default_region: str = "us-east-1", target_region: str = "all") -> List[Dict[str, Any]]:
        # PRE-RESOLVE STS AssumeRole ONCE:
        # Avoids 200 redundant blocking network calls to STS during the parallel worker fan-out.
        if credentials.get('assume_role_arn'):
            def _resolve_sts():
                session = self.session_manager.create_session(credentials, default_region)
                creds = session.get_credentials().get_frozen_credentials()
                return {
                    'aws_access_key_id': creds.access_key,
                    'aws_secret_access_key': creds.secret_key,
                    'aws_session_token': creds.token
                }
            credentials = await asyncio.to_thread(_resolve_sts)

        if target_region and target_region != "all":
            # Support comma-separated multi-region e.g. "ap-south-1,us-east-1"
            active_regions = [r.strip() for r in target_region.split(',') if r.strip()]
        else:
            active_regions = await asyncio.to_thread(self.get_active_regions, credentials, default_region)
            
        logger.info(f"[AWS Scanner] Scanning {len(active_regions)} regions natively via asyncio...")
        
        
        all_resources: List[Dict[str, Any]] = []
        
        # 1. Pre-fetch available regions for each service to filter out Dead Endpoints (O(1) checks)
        session = self.session_manager.create_session(credentials, default_region)
        service_regions = {}
        for handler in self.handlers:
            svc_name = HANDLER_SERVICE_MAP.get(type(handler).__name__)
            if svc_name:
                try:
                    service_regions[svc_name] = set(session.get_available_regions(svc_name))
                except Exception:
                    service_regions[svc_name] = set(active_regions)
            else:
                service_regions[type(handler).__name__] = set(active_regions)
                
        tasks = []
        for region in active_regions:
            for handler in self.handlers:
                svc_name = HANDLER_SERVICE_MAP.get(type(handler).__name__)
                
                # If the service is NOT available in this region, skip making the network call entirely
                if svc_name and region not in service_regions.get(svc_name, set()):
                    continue
                    
                async def scan_wrapper(h=handler, r=region):
                    try:
                        return await h.async_scan_region(self.session_manager, credentials, r, executor=_SCANNER_EXECUTOR)
                    except Exception as e:
                        return e
                        
                tasks.append(scan_wrapper())
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 3. Filter exceptions and flatten valid results
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"[AWS Scanner] Worker thread raised unhandled exception: {res}")
            elif isinstance(res, list):
                all_resources.extend(res)
                    
        
        logger.info(f"[AWS Scanner] Parallel scan complete. Discovered {len(all_resources)} total resources.")
        return all_resources

async def scan_all_resources_parallel(credentials: dict, default_region: str = "us-east-1", target_region: str = "all") -> List[Dict[str, Any]]:
    scanner = AWSParallelScanner()
    return await scanner.scan_all_resources_parallel(credentials, default_region, target_region)


import concurrent.futures
from datetime import datetime, timedelta, timezone
import json

class ResourceExplorerScanner:
    # Pricing API logic removed as per user request
    def get_aggregator_region(self, session, default_region='us-east-1') -> str:
        try:
            print(f"Discovering Resource Explorer AGGREGATOR region using baseline {default_region}...")
            re_client = session.client('resource-explorer-2', region_name=default_region)
            
            response = re_client.list_indexes(Type='AGGREGATOR')
            idx_list = response.get('Indexes', [])
            
            if not idx_list:
                raise ValueError("No AGGREGATOR index profile returned by the client. Ensure AWS Resource Explorer is enabled and aggregated.")
                
            agg_region = idx_list[0].get('Region')
            if not agg_region:
                raise ValueError("AGGREGATOR index found but missing 'Region' property.")
                
            return agg_region
        except Exception as e:
            print(f"WARNING: Failed to auto-discover AWS Resource Explorer aggregator region: {e}")
            raise

    def scan(self, session, region: str = None) -> list[dict]:
        try:
            baseline_region = region if region else 'us-east-1'
            agg_region = self.get_aggregator_region(session, baseline_region)

            print(f"Attempting AWS Resource Explorer list_resources in aggregator region {agg_region}...")
            client = session.client('resource-explorer-2', region_name=agg_region)
            
            # Fetch a ViewArn to use for list_resources
            views_resp = client.list_views()
            views = views_resp.get('Views', [])
            if not views:
                raise ValueError("No views found for AWS Resource Explorer in this region.")
            view_arn = views[0]
            
            raw_resources = []
            paginator = client.get_paginator('list_resources')
            for page in paginator.paginate(ViewArn=view_arn):
                for res in page.get("Resources", []):
                    raw_resources.append(res)
                    
            resources = []
            for res in raw_resources:
                arn = res.get("Arn")
                res_type = res.get("ResourceType")
                res_region = res.get("Region")
                
                # Static local billing evaluation
                NON_BILLABLE_AWS_TYPES = {
                    "aws::ec2::securitygroup", "aws::ec2::vpc", "aws::ec2::subnet", "aws::ec2::routetable", "aws::ec2::internetgateway", "aws::iam::role", "aws::iam::policy",
                    "ec2:vpc", "ec2:subnet", "ec2:security-group", "ec2:route-table", "ec2:network-acl", "ec2:internet-gateway", "ec2:dhcp-options", "ec2:key-pair", "iam:policy", "iam:role"
                }
                is_billable = res_type.lower() not in NON_BILLABLE_AWS_TYPES
                billing_tier = 'Standard' if is_billable else 'Free/Config'
                billable = is_billable
                
                name = None
                tags_dict = {}
                for prop in res.get('Properties', []):
                    if prop.get('Name') == 'tags':
                        try:
                            # Search API has Data as list of dicts, let's parse safely
                            data = prop.get('Data')
                            if isinstance(data, list):
                                for tag in data:
                                    if isinstance(tag, dict):
                                        k = tag.get('Key')
                                        v = tag.get('Value')
                                        if k and v:
                                            tags_dict[k] = v
                                            if k.lower() == 'name':
                                                name = v
                            elif isinstance(data, str):
                                # Sometimes Properties data is stringified JSON depending on API
                                try:
                                    parsed_data = json.loads(data)
                                    if isinstance(parsed_data, list):
                                        for tag in parsed_data:
                                            if isinstance(tag, dict):
                                                k = tag.get('Key')
                                                v = tag.get('Value')
                                                if k and v:
                                                    tags_dict[k] = v
                                                    if k.lower() == 'name':
                                                        name = v
                                except Exception:
                                    pass
                        except Exception:
                            pass
                            
                if not name:
                    name = arn.split('/')[-1] if '/' in arn else arn.split(':')[-1]
                
                linked_account = None
                try:
                    parts = arn.split(':')
                    if len(parts) >= 5 and parts[4]:
                        linked_account = parts[4]
                except Exception:
                    pass
                
                first_seen_date = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST")
                        
                resources.append({
                    "native_id": arn,
                    "name": name,
                    "tags": json.dumps(tags_dict),
                    "type": res_type,
                    "region": res_region,
                    "linked_account": linked_account,
                    "billable": billable,
                    "is_billable": is_billable,
                    "billing_tier": billing_tier,
                    "first_seen_date": first_seen_date
                })
                    
            if not resources:
                raise Exception("Resource Explorer search returned 0 resources")
            
            print(f"Resource Explorer found {len(resources)} resources.")
            return resources
                
        except Exception as e:
            print(f"AWS Resource Explorer Sync Failed: {e}")
            raise Exception(f"AWS Resource Explorer Sync Failed: {str(e)}")


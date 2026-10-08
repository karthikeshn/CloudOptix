import os
import json
import logging
from typing import Dict, Any, List
from google.oauth2 import service_account
from google.cloud import asset_v1

logger = logging.getLogger("cloudpulse.gcp_scanner")

class GCPProjectScanner:
    def scan_all_resources(self, credentials, project_id: str) -> List[Dict[str, Any]]:
        """
        Sweeps the ENTIRE GCP project hierarchy across all micro-regions 
        using the native Google Cloud Asset Inventory API framework.
        """
        try:
            self.asset_client = asset_v1.AssetServiceClient(credentials=credentials)
            self.project_id = project_id
        except Exception as e:
            logger.error(f"GCP Scanner initialization crashed: {str(e)}")
            raise e
            
        parsed_resources = []
        try:
            parent = f"projects/{self.project_id}"
            logger.info(f"Initiating Google Cloud inventory search loop for: {parent}")
            
            # Request all compute, network, and storage nodes inside our project boundary
            response_pager = self.asset_client.search_all_resources(
                request={"scope": parent, "query": ""}
            )

            for asset in response_pager:
                region = asset.location if asset.location else "global"
                labels = getattr(asset, "labels", {}) or {}

                tags_dict = dict(labels)
                NON_BILLABLE_GCP_TYPES = {"compute.googleapis.com/firewall", "compute.googleapis.com/network", "compute.googleapis.com/subnetwork", "iam.googleapis.com/role", "iam.googleapis.com/policy"}
                is_billable = asset.asset_type.lower() not in NON_BILLABLE_GCP_TYPES
                billing_tier = 'Standard' if is_billable else 'Free/Config'
                
                # Dynamic safe naming fallback
                friendly_name = asset.display_name or asset.name.split('/')[-1]
                
                parsed_resources.append({
                    # Core Unified Keys (Keeps AWS/Azure/GCP router uniform)
                    'arn': asset.name, 
                    'resource_name': friendly_name,
                    'is_billable': is_billable,
                    
                    # Your Custom Database Schema Fields
                    'native_id': asset.name,
                    'name': friendly_name,
                    'tags': json.dumps(tags_dict),
                    'type': asset.asset_type,
                    'region': region,
                    'linked_account': asset.project,
                    'billable': is_billable,
                    'billing_tier': billing_tier,
                    'raw_payload': {
                        'name': asset.name,
                        'asset_type': asset.asset_type,
                        'project': asset.project,
                        'description': asset.description
                    }
                })

            logger.info(f"GCP sync completed. Found {len(parsed_resources)} active nodes.")
            return parsed_resources

        except Exception as e:
            logger.error(f"GCP Cloud Asset Inventory exploration sweep failed: {str(e)}")
            raise e

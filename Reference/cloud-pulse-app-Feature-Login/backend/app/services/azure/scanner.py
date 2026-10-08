from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
import json

class AzureResourceGraphScanner:
    def scan(self, session, subscription_id: str = None) -> list[dict]:
        # 'session' here is the credential returned from AzureAuthManager.create_session
        print(f"Attempting Azure Resource Graph query for subscription: {subscription_id or 'All Accessible'}")
        client = ResourceGraphClient(session)
        query = "Resources | project id, name, type, location, resourceGroup, subscriptionId, tags"
        
        # If subscription_id is provided, restrict to it. Otherwise, ARG searches all accessible subscriptions.
        options = QueryRequestOptions(result_format="objectArray")
        results = []
        
        while True:
            kwargs = {
                "query": query,
                "options": options
            }
            if subscription_id:
                kwargs["subscriptions"] = [subscription_id]
                
            request = QueryRequest(**kwargs)
            response = client.resources(request)
            
            if response.data:
                results.extend(response.data)
                
            # Check for pagination token to bypass 1,000 item limit
            if getattr(response, 'skip_token', None):
                options.skip_token = response.skip_token
            else:
                break
        
        parsed_resources = []
        for res in results:
            res_type = str(res.get('type', '')).lower()
            tags_dict = res.get('tags') or {}
            
            # Simple heuristic for billable vs non-billable
            non_billable_types = [
                'microsoft.network/virtualnetworks',
                'microsoft.network/networksecuritygroups',
                'microsoft.network/routetables',
                'microsoft.authorization/roleassignments',
                'microsoft.resources/resourcegroups'
            ]
            
            is_billable = res_type.lower() not in [t.lower() for t in non_billable_types]
            billing_tier = 'Standard' if is_billable else 'Free/Config'
                
            parsed_resources.append({
                'native_id': res.get('id'),
                'name': res.get('name'),
                'tags': json.dumps(tags_dict),
                'type': res.get('type'),
                'region': res.get('location'),
                'linked_account': res.get('subscriptionId'),
                'billable': is_billable,
                'billing_tier': billing_tier
            })
            
        print(f"Azure Resource Graph found {len(parsed_resources)} resources.")
        return parsed_resources

import asyncio
from azure.identity import ClientSecretCredential, ManagedIdentityCredential
from azure.core.exceptions import ClientAuthenticationError

class AzureAuthManager:
    def create_session(self, credentials: dict):
        if credentials.get('use_managed_identity'):
            client_id = credentials.get('user_assigned_id')
            if client_id:
                return ManagedIdentityCredential(client_id=client_id)
            return ManagedIdentityCredential()
        else:
            return ClientSecretCredential(
                tenant_id=credentials.get('tenant_id', '').strip(),
                client_id=credentials.get('client_id', '').strip(),
                client_secret=credentials.get('client_secret', '').strip()
            )

    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        def _test():
            try:
                cred = self.create_session(credentials)
                # Request a token for Azure Management API to verify credentials
                token = cred.get_token("https://management.azure.com/.default")
                if token:
                    return True, ""
                return False, "Failed to retrieve token."
            except ClientAuthenticationError as e:
                return False, f"Authentication Error: {getattr(e, 'message', str(e))}"
            except Exception as e:
                return False, str(e)
                
        return await asyncio.to_thread(_test)

import json
import logging
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

class GCPAuthManager:
    def create_session(self, credentials: dict):
        """
        Creates a google.oauth2 Credentials object directly from the provided service account JSON.
        """
        service_account_json_str = credentials.get("service_account_json")
        if not service_account_json_str:
            raise ValueError("Missing 'service_account_json' in credentials payload.")
            
        try:
            key_dict = json.loads(service_account_json_str)
            if not key_dict.get("project_id"):
                raise ValueError("The provided JSON payload is missing the required 'project_id' attribute.")
                
            creds = service_account.Credentials.from_service_account_info(key_dict)
            return creds, key_dict.get("project_id")
        except json.JSONDecodeError:
            raise ValueError("Invalid configuration profile format. Please paste a clean Service Account Key JSON.")
        except Exception as e:
            raise ValueError(f"Failed to create GCP session: {str(e)}")

    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        """
        Tests the GCP credentials by attempting to parse them and create a credentials object.
        """
        try:
            self.create_session(credentials)
            return True, ""
        except Exception as e:
            logger.error(f"GCP connection test failed: {e}")
            return False, str(e)

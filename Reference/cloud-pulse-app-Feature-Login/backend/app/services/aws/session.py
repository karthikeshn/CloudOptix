import asyncio
import os
import boto3
import botocore.session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

BOTO3_CONFIG = Config(
    retries={
        "max_attempts": 10,
        "mode": "adaptive"
    },
    max_pool_connections=50
)

class AWSSessionManager:
    def __init__(self):
        # Cache the core botocore session globally. 
        # This prevents 187 threads from simultaneously reading and parsing AWS JSON schemas from disk,
        # which completely locks the Python GIL for 2 minutes!
        self._bc_session = botocore.session.get_session()

    def create_session(self, credentials: dict, region: str = None):
        bc_session = self._bc_session
        if credentials.get('aws_access_key_id') or credentials.get('assume_role_arn'):
            bc_session.set_config_variable('credentials_file', os.devnull)

        if credentials.get('assume_role_arn'):
            sts_params = {
                'region_name': 'us-east-1',
                'config': BOTO3_CONFIG
            }
            if credentials.get('aws_access_key_id'):
                sts_params['aws_access_key_id'] = credentials['aws_access_key_id']
                sts_params['aws_secret_access_key'] = credentials['aws_secret_access_key']
            if credentials.get('aws_session_token'):
                sts_params['aws_session_token'] = credentials['aws_session_token'].strip()
                
            sts = boto3.client('sts', **sts_params)

            assume_params = {'RoleArn': credentials['assume_role_arn'], 'RoleSessionName': 'ControlModuleSession', 'DurationSeconds': 3600}
            if credentials.get('external_id'):
                assume_params['ExternalId'] = credentials['external_id']

            creds = sts.assume_role(**assume_params)['Credentials']
            session = boto3.Session(
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken'],
                region_name=region,
                botocore_session=bc_session
            )
        elif credentials.get('use_iam_role'):
            session = boto3.Session(region_name=region, botocore_session=bc_session)
        else:
            params = {
                'aws_access_key_id': credentials.get('aws_access_key_id', '').strip() if credentials.get('aws_access_key_id') else None,
                'aws_secret_access_key': credentials.get('aws_secret_access_key', '').strip() if credentials.get('aws_secret_access_key') else None,
                'region_name': region,
                'botocore_session': bc_session
            }
            if credentials.get('aws_session_token'):
                params['aws_session_token'] = credentials.get('aws_session_token', '').strip()
            session = boto3.Session(**params)
            
        # Monkey-patch session.client to globally inject Adaptive Rate Limiting config
        # into ALL clients instantiated by any Handler using this session
        original_client = session.client
        def custom_client(service_name, **kwargs):
            if 'config' not in kwargs:
                kwargs['config'] = BOTO3_CONFIG
            return original_client(service_name, **kwargs)
        session.client = custom_client
        
        return session
        
    def get_client(self, session, service_name: str, region_name: str = None):
        """Helper to create a boto3 client from the session with the global config attached."""
        return session.client(service_name, region_name=region_name, config=BOTO3_CONFIG)

    async def test_connection(self, credentials: dict) -> tuple[bool, str]:
        def _test():
            try:
                session = self.create_session(credentials, credentials.get('default_region', 'us-east-1'))
                sts = self.get_client(session, 'sts', region_name='us-east-1')
                sts.get_caller_identity()
                return True, ""
            except (BotoCoreError, ClientError) as e:
                err = str(e)
                
                # AWS unfortunately returns 'InvalidClientTokenId' for BOTH a bad Access Key 
                # AND an expired/bad Session Token. We must infer the cause based on input.
                if "InvalidClientTokenId" in err or "InvalidSecurityToken" in err or "ExpiredToken" in err:
                    if credentials.get('aws_session_token'):
                        return False, "AWS Session Token has expired or is invalid."
                    return False, "Invalid AWS Access Key ID."
                    
                if "InvalidAccessKeyId" in err:
                    return False, "Invalid AWS Access Key ID."
                if "SignatureDoesNotMatch" in err:
                    return False, "Invalid AWS Secret Key."
                return False, err
                
        return await asyncio.to_thread(_test)

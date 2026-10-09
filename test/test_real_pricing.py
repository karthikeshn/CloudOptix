import os
import boto3
from dotenv import load_dotenv

# Load the real credentials
load_dotenv(r"d:\FinOpsDashboard\backend\.env")
real_access = os.environ.get("REAL_AWS_ACCESS_KEY_ID")
real_secret = os.environ.get("REAL_AWS_SECRET_ACCESS_KEY")

print(f"[System] Testing Real Pricing API without Moto active...")
print(f"[System] Loaded Credentials. Key starts with: {str(real_access)[:5]}...")

try:
    # 1. Create a real boto3 client (Zero Moto Interception here!)
    pricing_client = boto3.client(
        'pricing', 
        region_name='us-east-1',
        aws_access_key_id=real_access,
        aws_secret_access_key=real_secret
    )
    
    # 2. Call the exact same logic our production script uses
    print("[System] Connecting to real AWS Pricing Internet Endpoint...")
    response = pricing_client.get_products(
        ServiceCode='AmazonRDS',
        Filters=[
            {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': 'US East (N. Virginia)'},
            {'Type': 'TERM_MATCH', 'Field': 'volumeType', 'Value': 'General Purpose (SSD)'},
            {'Type': 'TERM_MATCH', 'Field': 'productFamily', 'Value': 'Database Storage'}
        ],
        MaxResults=1
    )
    
    print("\nSUCCESS! Hit the real AWS Internet!")
    print(f"AWS Raw Response snippet: {str(response)[:200]}...")
except Exception as e:
    print(f"\nFAILED to hit AWS. Reason: {e}")
    print("If it says 'InvalidClientTokenId' or 'UnrecognizedClientException', it means the AWS internet connection WORKED, but your dummy keys in .env were rejected by Amazon!")

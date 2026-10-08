import boto3
import json

def test_ec2_pricing_api():
    print("Connecting to AWS Pricing API (us-east-1)...")
    pricing_client = boto3.client('pricing', region_name='us-east-1')
    
    instance_type = 'm5.large'
    region_name = 'US East (N. Virginia)'
    
    print(f"Fetching On-Demand Linux price for {instance_type} in {region_name}...\n")
    
    try:
        response = pricing_client.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region_name},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'}
            ],
            MaxResults=1
        )
        
        price_list = response.get('PriceList', [])
        
        if not price_list:
            print("No pricing data found. Please check filters.")
            return
            
        # Parse the nested JSON
        price_data = json.loads(price_list[0])
        terms = price_data.get('terms', {}).get('OnDemand', {})
        
        rate = None
        for term_key, term_val in terms.items():
            for dimension_key, dimension_val in term_val.get('priceDimensions', {}).items():
                rate_usd = dimension_val.get('pricePerUnit', {}).get('USD')
                if rate_usd:
                    rate = float(rate_usd)
                    
        if rate is not None:
            print(f"[SUCCESS] The exact market rate is: ${rate:.4f} per hour.")
            print(f"   (That equals roughly ${rate * 730:.2f} per month)")
        else:
            print("[ERROR] Failed to parse the USD rate from the JSON.")
            
    except Exception as e:
        print(f"[ERROR] Error calling AWS Pricing API: {e}")
        print("Note: You must have AWS credentials configured locally (e.g. ~/.aws/credentials) for boto3 to authenticate!")

if __name__ == "__main__":
    test_ec2_pricing_api()

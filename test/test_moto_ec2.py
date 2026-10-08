import boto3
from moto import mock_aws

@mock_aws
def test_fake_aws_environment():
    print("1. Moto interceptor activated! (We are completely offline)")
    
    # Even though we use boto3, Moto intercepts this. It won't ask for credentials!
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    
    print("2. Creating a fake EC2 instance in RAM...")
    ec2_client.run_instances(
        ImageId='ami-12c6146b',
        MinCount=1,
        MaxCount=1,
        InstanceType='t3.micro',
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': [{'Key': 'Name', 'Value': 'MyFakeFinOpsInstance'}]
        }]
    )
    
    print("3. Scanning our fake AWS account...")
    response = ec2_client.describe_instances()
    
    instances_found = 0
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances_found += 1
            instance_id = instance['InstanceId']
            instance_type = instance['InstanceType']
            print(f"   -> FOUND IT! ID: {instance_id} | Type: {instance_type}")
            
    print(f"\n[SUCCESS] Boto3 found {instances_found} instances without ever touching the internet.")

if __name__ == '__main__':
    test_fake_aws_environment()

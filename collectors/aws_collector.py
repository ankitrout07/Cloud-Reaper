import boto3
import os
from dotenv import load_dotenv

load_dotenv()

class AWSCollector:
    def __init__(self):
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        self.ec2 = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=self.region
        )

    def get_ec2_inventory(self):
        """Lists all EC2 instances and their types."""
        instances = self.ec2.describe_instances()
        inventory = []
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                inventory.append({
                    'id': instance['InstanceId'],
                    'type': instance['InstanceType'],
                    'state': instance['State']['Name'],
                    'tags': instance.get('Tags', [])
                })
        return inventory

    def get_orphaned_volumes(self):
        """Identifies EBS volumes with state 'available' (not attached)."""
        volumes = self.ec2.describe_volumes(
            Filters=[{'Name': 'status', 'Values': ['available']}]
        )
        orphans = []
        for vol in volumes['Volumes']:
            orphans.append({
                'id': vol['VolumeId'],
                'size': vol['Size'],
                'type': vol['VolumeType'], # e.g., gp3
                'iops': vol.get('Iops', 0)
            })
        return orphans

if __name__ == "__main__":
    collector = AWSCollector()
    print(f"--- Scanning AWS EC2 in {collector.region} ---")
    instances = collector.get_ec2_inventory()
    for ins in instances:
        print(f"Found Instance: {ins['id']} [{ins['type']}] - State: {ins['state']}")

    print("\n--- Hunting Orphaned EBS Volumes ---")
    orphans = collector.get_orphaned_volumes()
    if not orphans:
        print("No orphaned volumes found. AWS storage is optimized.")
    for vol in orphans:
        print(f"[!] REAPER TARGET: {vol['id']} ({vol['size']}GB) - Type: {vol['type']}")
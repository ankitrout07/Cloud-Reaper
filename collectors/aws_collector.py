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
        try:
            instances = self.ec2.describe_instances()
            inventory = []
            for reservation in instances.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    inventory.append({
                        'id': instance['InstanceId'],
                        'type': instance['InstanceType'],
                        'state': instance['State']['Name']
                    })
            return inventory
        except Exception:
            return []

    def get_orphaned_volumes(self):
        try:
            volumes = self.ec2.describe_volumes(
                Filters=[{'Name': 'status', 'Values': ['available']}]
            )
            orphans = []
            for vol in volumes.get('Volumes', []):
                orphans.append({
                    'id': vol['VolumeId'],
                    'size': vol['Size'],
                    'type': vol['VolumeType']
                })
            return orphans
        except Exception:
            return []

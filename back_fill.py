import boto3
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal

def backfill_missing_netload():
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('GridTelemetryState')

    print("Scanning DynamoDB for historical records missing 'NetLoad'...")

    response = table.query(
        KeyConditionExpression=Key('MetricID').eq('BPA-NW'),
        FilterExpression=Attr('NetLoad').not_exists() & Attr('Load').exists() & Attr('Wind').exists()
    )

    items = response.get('Items', [])
    updated_count = 0

    while True:
        for item in items:
            ts = item['Timestamp']
            
            load = float(item['Load'])
            wind = float(item['Wind'])
            net_load = load - wind

            table.update_item(
                Key={
                    'MetricID': 'BPA-NW',
                    'Timestamp': ts
                },
                UpdateExpression="SET NetLoad = :val",
                ExpressionAttributeValues={
                    ':val': Decimal(str(net_load))
                }
            )
            
            updated_count += 1
            if updated_count % 100 == 0:
                print(f"Successfully updated {updated_count} records so far...")

        if 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('MetricID').eq('BPA-NW'),
                FilterExpression=Attr('NetLoad').not_exists() & Attr('Load').exists() & Attr('Wind').exists(),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
        else:
            break

    print(f"Backfill Complete! A total of {updated_count} historical records were enriched with NetLoad.")

if __name__ == '__main__':
    backfill_missing_netload()
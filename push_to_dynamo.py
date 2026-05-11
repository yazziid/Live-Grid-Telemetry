import pandas as pd
import boto3
from decimal import Decimal

def bulk_load_to_dynamodb(csv_filepath):
    print(f"Reading data from {csv_filepath}...")
    
    try:
        df = pd.read_csv(csv_filepath)
    except FileNotFoundError:
        print(f"Error: Could not find {csv_filepath}. Please make sure it's in the same folder.")
        return

    if 'Date/Time' in df.columns:
        df['Date/Time'] = pd.to_datetime(df['Date/Time'])
    else:
        print("Error: 'Date/Time' column not found in the CSV.")
        return

    print("Connecting to AWS DynamoDB...")
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('GridTelemetryState')

    print("Starting bulk upload...")
    uploaded_count = 0

    with table.batch_writer() as batch:
        for index, row in df.iterrows():
            
            timestamp = int(row['Date/Time'].timestamp())
            
            item = {
                'MetricID': 'BPA-NW',
                'Timestamp': timestamp
            }
            
            for col in df.columns:
                if col == 'Date/Time':
                    continue
                
                val = row[col]
                if pd.notna(val):
                    item[col] = Decimal(str(val))
                    
            batch.put_item(Item=item)
            uploaded_count += 1
            
            if uploaded_count % 1000 == 0:
                print(f"⏳ Uploaded {uploaded_count} records...")

    print(f"Success! All {uploaded_count} records have been pushed to DynamoDB.")

if __name__ == "__main__":
    bulk_load_to_dynamodb("bpa_generation_data.csv")
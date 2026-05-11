from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import urllib.request
import pandas as pd
from io import StringIO
import ssl
import json
from kafka import KafkaProducer
import boto3  
from decimal import Decimal

ssl_context = ssl._create_unverified_context()

def fetch_latest_bpa_data():
    urls = [
        "https://transmission.bpa.gov/Business/Operations/wind/baltwg3.txt",
        "https://transmission.bpa.gov/Business/Operations/wind/tverbspt.txt"
    ]
    
    dataframes = []
    for url in urls:
        response = urllib.request.urlopen(url, context=ssl_context)
        lines = response.read().decode('utf-8').split('\n')
        header_idx = next(i for i, line in enumerate(lines) if line.startswith('Date/Time'))
        csv_data = '\n'.join(lines[header_idx:])
        
        df = pd.read_csv(StringIO(csv_data), sep='\t')
        df.columns = df.columns.str.strip()
        df['Date/Time'] = pd.to_datetime(df['Date/Time'].str.strip(), format='%m/%d/%Y %H:%M', errors='coerce')
        df = df.set_index('Date/Time').dropna(how='all')
        dataframes.append(df)

    merged_df = pd.concat(dataframes, axis=1)
    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
    
    latest_row = merged_df.iloc[-1]
    
    payload = {
        "MetricID": "BPA-NW",
        "Timestamp": int(latest_row.name.timestamp()),
        "Load": float(latest_row.get('Load', 0)),
        "Wind": float(latest_row.get('Wind', 0)),
        "Hydro": float(latest_row.get('Hydro', 0)),
        "Fossil/Biomass": float(latest_row.get('Fossil/Biomass', 0)),
        "Solar": float(latest_row.get('Solar', 0)),           
        "Interchange": float(latest_row.get('Interchange', 0))
    }
    return payload

def push_to_kafka_and_dynamo():
    payload = fetch_latest_bpa_data()
    print(f"Scraped Payload: {payload}")
    
    producer = KafkaProducer(
        bootstrap_servers=['kafka:29092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    producer.send('grid-telemetry', payload)
    producer.flush()
    print("Successfully published to Kafka!")

    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1') 
        table = dynamodb.Table('GridTelemetryState')

        dynamo_item = {
            'MetricID': payload['MetricID'],
            'Timestamp': payload['Timestamp'],
            'Load': Decimal(str(payload['Load'])),
            'Wind': Decimal(str(payload['Wind'])),
            'Hydro': Decimal(str(payload['Hydro'])),
            'Fossil/Biomass': Decimal(str(payload['Fossil/Biomass'])),
            'Solar': Decimal(str(payload['Solar'])),            
            'Interchange': Decimal(str(payload['Interchange'])),
            'Status': 'RAW' # Useful for filtering later
        }

        table.put_item(Item=dynamo_item)
        print(f"Successfully inserted raw data into DynamoDB for timestamp {payload['Timestamp']}!")
    except Exception as e:
        print(f"Failed to insert into DynamoDB: {e}")

default_args = {
    'owner': 'data-engineer',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

with DAG(
    'bpa_kafka_ingestion',
    default_args=default_args,
    description='Fetch BPA data and push to Kafka + DynamoDB',
    schedule_interval=timedelta(minutes=5),
    catchup=False
) as dag:

    ingest_task = PythonOperator(
        task_id='scrape_and_publish',
        python_callable=push_to_kafka_and_dynamo
    )
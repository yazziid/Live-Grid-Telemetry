import pandas as pd
import urllib.request
from io import StringIO
import ssl
import boto3
from decimal import Decimal

ssl_context = ssl._create_unverified_context()

def extract_table(url):
    response = urllib.request.urlopen(url, context=ssl_context)
    raw_text = response.read().decode('utf-8')
    lines = raw_text.split('\n')
    header_idx = next(i for i, line in enumerate(lines) if line.startswith('Date/Time'))
    csv_data = '\n'.join(lines[header_idx:])
    
    df = pd.read_csv(StringIO(csv_data), sep='\t')
    df.columns = df.columns.str.strip()
    df['Date/Time'] = pd.to_datetime(df['Date/Time'].str.strip(), format='%m/%d/%Y %H:%M', errors='coerce')
    df = df.set_index('Date/Time')
    df = df[df.index.notnull()]
    
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df = df.interpolate(method='time')
    return df

def fetch_and_merge(urls):
    dataframes = []
    
    for url in urls:
        df = extract_table(url)
        dataframes.append(df)

    merged_df = pd.concat(dataframes, axis=1)
    
    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
    
    return merged_df


def save_to_csv(df, csv_path):
    df.to_csv(csv_path, index=True)
    

def push_to_dynamodb(df):
    print("Initiating connection to AWS DynamoDB...")
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('GridTelemetryState')
    
    with table.batch_writer() as batch:
        for index, row in df.iterrows():
            timestamp = int(index.timestamp())
            
            item = {
                'MetricID': 'BPA-NW',
                'Timestamp': timestamp
            }
            
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    item[col] = Decimal(str(val))
                    
            batch.put_item(Item=item)
            
    print(f"Successfully pushed {len(df)} records to DynamoDB.")


if __name__ == '__main__':
      
    urls = [
        "https://transmission.bpa.gov/Business/Operations/wind/baltwg3.txt",
        "https://transmission.bpa.gov/Business/Operations/wind/tverbspt.txt"
    ]
    
    final_df = fetch_and_merge(urls)
    push_to_dynamodb(final_df)

    #save_to_csv(final_df, 'bpa_generation_data.csv')

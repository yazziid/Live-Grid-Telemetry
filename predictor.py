import time
import torch
import boto3
import pandas as pd
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from pytorch_forecasting import TemporalFusionTransformer

CHECKPOINT_PATH = "logs/lightning_logs/version_9/checkpoints/best_model.ckpt"
print("Loading TFT model...")
model = TemporalFusionTransformer.load_from_checkpoint(CHECKPOINT_PATH)
model.eval()

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('GridTelemetryState')

def fetch_historical_context(days = 8):
    print("Fetching historical context from DynamoDB...")
    past_timestamp = int(time.time()) - (days * 24 * 3600) # 8 days
    
    response = table.query(
        KeyConditionExpression=Key('MetricID').eq('BPA-NW') & Key('Timestamp').gt(past_timestamp)
    )
    items = response.get('Items', [])
    
    while 'LastEvaluatedKey' in response:
        response = table.query(
            KeyConditionExpression=Key('MetricID').eq('BPA-NW') & Key('Timestamp').gt(past_timestamp),
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response.get('Items', []))
        
    if not items:
        return pd.DataFrame()
        
    df = pd.DataFrame(items)
    return df

def prepare_inference_data(df):
    df = df.copy()
    
    df['Timestamp'] = pd.to_numeric(df['Timestamp'], errors='coerce')
    df['Date/Time'] = pd.to_datetime(df['Timestamp'], unit='s')
    df = df.set_index('Date/Time')
    
    numeric_cols = ['Load', 'Wind', 'Hydro', 'Fossil/Biomass', 'Solar', 'Nuclear']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        else:
            df[col] = 0.0
            
    df = df[numeric_cols].resample('5min').mean()
    df = df.interpolate(method='time')
    
    df['hour'] = df.index.hour.astype(str)
    df['day_of_week'] = df.index.dayofweek.astype(str)
    df['agency'] = 'BPA'
    
    df['time_idx'] = (df.index - df.index.min()).total_seconds() // 300
    df['time_idx'] = df['time_idx'].astype(int)
    
    df['Net_Load'] = df['Load'] - (df['Wind'] + df['Solar'])
    
    df = df.dropna()
    
    return df.tail(2016)


def run_predictions():
    raw_df = fetch_historical_context()
    if raw_df.empty:
        print("No data found in DynamoDB.")
        return

    latest_ts = int(raw_df.sort_values('Timestamp').iloc[-1]['Timestamp'])
    
    print(f"Preparing data sequence for timestamp: {latest_ts}")
    inference_df = prepare_inference_data(raw_df)
    
    if len(inference_df) < 1008: # min_encoder_length checking
        print(f"Not enough historical data yet. Have {len(inference_df)} rows, need at least 1008.")
        return

    print("Running TFT Inference for Scenarios...")
    with torch.no_grad():
        predictions = model.predict(inference_df, mode="quantiles")
            
    best_case = predictions[0, :, 1].tolist()      # 10th Percentile 
    expected = predictions[0, :, 3].tolist()       # 50th Percentile 
    worst_case = predictions[0, :, 5].tolist()     # 90th Percentile

    dyn_best = [Decimal(str(v)) for v in best_case]
    dyn_expected = [Decimal(str(v)) for v in expected]
    dyn_worst = [Decimal(str(v)) for v in worst_case]
    
    print("Pushing all 3 scenarios to DynamoDB...")
    table.update_item(
        Key={'MetricID': 'BPA-NW', 'Timestamp': latest_ts},
        UpdateExpression="SET Forecast_Best = :b, Forecast_Expected = :e, Forecast_Worst = :w",
        ExpressionAttributeValues={
            ':b': dyn_best,
            ':e': dyn_expected,
            ':w': dyn_worst
        }
    )
    print("Full forecast pushed to DynamoDB successfully!\n")
    
if __name__ == "__main__":
    run_predictions()
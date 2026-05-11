import streamlit as st
import boto3
from boto3.dynamodb.conditions import Key
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Grid Digital Twin", layout="wide")
st.title(" Renewable Energy Digital Twin")
st.markdown("Live Telemetry & Historical Trends from the BPA Grid")

st.sidebar.header("Dashboard Controls")

default_start = datetime.now().date() - timedelta(days=7)
default_end = datetime.now().date()

date_range = st.sidebar.date_input(
    "Select Date Range", 
    value=(default_start, default_end),
    max_value=datetime.now().date()
)

freq_mapping = {
    "5-Min"  : None,
    "15-Min" : "15min",
    "30-Min" : "30min",
    "Hourly" : "H",
    "Daily"  : "D"
}
selected_freq_label = st.sidebar.selectbox(
    "Select Resolution Frequency", 
    options=list(freq_mapping.keys()),
    index=0 # "Default is 5min"
)
selected_freq = freq_mapping[selected_freq_label]

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('GridTelemetryState')

def fetch_range_data(start_date, end_date, freq):
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
    
    response = table.query(
        KeyConditionExpression=Key('MetricID').eq('BPA-NW') & Key('Timestamp').between(start_ts, end_ts)
    )
    
    items = response.get('Items', [])
    if not items:
        return pd.DataFrame()
        
    df = pd.DataFrame(items)
    
    df['Timestamp'] = pd.to_datetime(pd.to_numeric(df['Timestamp'], errors='coerce'), unit='s')
    df = df.sort_values('Timestamp').set_index('Timestamp')
    
    numeric_cols = ['Load', 'Wind', 'Hydro', 'Fossil/Biomass', 'Solar', 'Interchange', 'NetLoad']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    if freq is not None:
        available_numeric = [c for c in numeric_cols if c in df.columns]
        df = df[available_numeric].resample(freq).mean()
        
    return df

if len(date_range) == 2:
    start_date, end_date = date_range
    
    with st.spinner('Fetching and aggregating grid data...'):
        df = fetch_range_data(start_date, end_date, selected_freq)

    if df.empty:
        st.warning(f"No data found between {start_date} and {end_date}.")
    else:
        latest = df.iloc[-1]
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        
        col1.metric("Total Load (MW)", f"{latest.get('Load', 0):,.0f}")
        col2.metric("Wind Gen (MW)", f"{latest.get('Wind', 0):,.0f}")
        col3.metric("Hydro Gen (MW)", f"{latest.get('Hydro', 0):,.0f}")
        col4.metric("Fossil/Biomass (MW)", f"{latest.get('Fossil/Biomass', 0):,.0f}")
        col5.metric("Solar (MW)", f"{latest.get('Solar', 0):,.0f}")
        col6.metric("Interchange (MW)", f"{latest.get('Interchange', 0):,.0f}")
        col7.metric("NetLoad (MW)", f"{latest.get('NetLoad', 0):,.0f}")
        
        st.divider()
        
        st.subheader(f"Generation Mix ({selected_freq_label} Average)")
        
        available_cols = [c for c in ['Load', 'Wind', 'Hydro', 'Fossil/Biomass', 'Solar', 'Interchange'] if c in df.columns]        
        
        selected_metrics = st.multiselect(
            "Select generation types to display:",
            options=available_cols,
            default=available_cols
        )
        
        if selected_metrics:
            chart_data = df[selected_metrics].dropna()
            st.line_chart(chart_data, use_container_width=True)
        else:
            st.info("Please select at least one metric from the dropdown above to view the chart.")

else:
    st.info("Please select both a start and end date from the calendar.")

if st.sidebar.button("Refresh Data"):
    st.rerun()

st.divider()
st.subheader("Net Load Forecast Scenarios")

if 'Forecast_Expected' in df.columns:
    valid_forecasts = df.dropna(subset=['Forecast_Expected'])
else:
    valid_forecasts = pd.DataFrame()

if not valid_forecasts.empty:
    last_prediction = valid_forecasts.iloc[-1]
    last_pred_time = last_prediction.name
    
    st.caption(f"Last prediction generated for grid time: {last_pred_time.strftime('%Y-%m-%d %H:%M')}")
    
    best_forecast = [float(x) for x in last_prediction['Forecast_Best']]
    expected_forecast = [float(x) for x in last_prediction['Forecast_Expected']]
    worst_forecast = [float(x) for x in last_prediction['Forecast_Worst']]

    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        
    with f_col1:
        st.metric("T + 6 (6 Hr)", f"{expected_forecast[71]:,.0f} MW", delta="Expected")
    with f_col2:
        st.metric("T + 12 (12 Hrs)", f"{expected_forecast[143]:,.0f} MW", delta="Expected")
    with f_col3:
        st.metric("T + 18 (18 Hrs)", f"{expected_forecast[215]:,.0f} MW", delta="Expected")
    with f_col4:
        st.metric("T + 24 (24 Hrs)", f"{expected_forecast[287]:,.0f} MW", delta="Expected")
        
    st.markdown("**48-Hour Trend: Actual vs. Predicted Net Load (With Confidence Bounds)**")
    
    recent_history = df.loc[:last_pred_time, 'NetLoad'].dropna().tail(288) 
    
    future_times = [last_pred_time + timedelta(minutes=5*(i+1)) for i in range(len(expected_forecast))]
    
    history_df = pd.DataFrame({'Actual Net Load': recent_history})
    
    forecast_df = pd.DataFrame({
        'Worst Case (P90)': worst_forecast,
        'Expected': expected_forecast,
        'Best Case (P10)': best_forecast
    }, index=future_times)
    
    combined_chart = pd.concat([history_df, forecast_df])
    
    # Red (Actual), Light Gray (Bounds), Blue (Expected)
    st.line_chart(
        combined_chart, 
        color=["#FF4B4B", "#D3D3D3", "#0068C9", "#D3D3D3"] 
    )
        
else:
    st.info("No historical predictions found in this date range.")

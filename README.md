# Temporal Grid Twin

A real-time data engineering and machine learning pipeline that ingests live energy telemetry from the Bonneville Power Administration (BPA) to generate probabilistic net-load forecasts.

## Overview

An end-to-end Digital Twin that ingests live energy telemetry to predict net load demands. By leveraging AWS cloud infrastructure and deep learning, the system provides grid operators with real-time "Best, Expected, and Worst-case" scenarios across a rolling 48-hour window, enabling data-driven decisions for grid balancing and load shedding.

## Tech Stack

- **Languages:** Python.

- **Infrastructure:** Docker, Terraform, AWS (EC2, DynamoDB).

- **Data Engineering:** Apache Airflow, Apache Kafka, Apache Flink.

- **ML Model:** Temporal Fusion Transformer (TFT) with Quantile Loss.

- **Dashboard:** Streamlit.

## System Architecture

## Installation and Usage

1. Cloud Setup

Ensure your AWS credentials are configured and deploy the infrastructure using the provided Terraform scripts.

2. Setting up the infrastructure

```
terraform init
```

```
terraform apply
```

3. Build containers

```
docker-compose build
```

```
docker-compose up -d
```

4. Initial run

```
python scrape_data.py
```

5. Run the predictions

```
python predictor.py
```

_Optional_: re-train model:

```
python train.py
```

6. Running the dashboard

Inside AWS, connect to the EC2 then run

```
streamlit run dashboard.py
```

_NOTE_: Make sure to copy app.py into dashboard.py

## Dataset

This project uses the BPA (Bonneville Power Administration) api, which can be found following this [link](https://transmission.bpa.gov/Business/Operations/Wind/default.aspx).

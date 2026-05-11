from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import WatermarkStrategy
import json
import boto3
from decimal import Decimal

def process_stream():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    jar_path = "file:///opt/flink/lib/flink-sql-connector-kafka-3.0.1-1.17.jar"
    env.add_jars(jar_path)

    source = KafkaSource.builder() \
        .set_bootstrap_servers("kafka:29092") \
        .set_topics("grid-telemetry") \
        .set_group_id("flink_grid_consumer_v3") \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    stream = env.from_source(source, WatermarkStrategy.no_watermarks(), "Kafka Source")

    def enrich_and_sink(message_str):
        try:
            data = json.loads(message_str)
            
            m_id = data.get('MetricID', 'BPA-NW')
            ts = int(data.get('Timestamp'))
            load = float(data.get('Load', 0))
            wind = float(data.get('Wind', 0))
            
            net_load = load - wind

            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
            table = dynamodb.Table('GridTelemetryState')
            
            table.update_item(
                Key={
                    'MetricID': m_id,
                    'Timestamp': ts
                },
                UpdateExpression="SET NetLoad = :val",
                ExpressionAttributeValues={
                    ':val': Decimal(str(net_load))
                }
            )
            
            result = f"ENRICHED: {m_id} at {ts} | NetLoad: {net_load}MW"
            print(result) 
            return result
        except Exception as e:
            return f"Error: {str(e)}"

    processed_stream = stream.map(enrich_and_sink, output_type=Types.STRING())
    processed_stream.print()

    env.execute("BPA-Realtime-Net-Load-Analyzer")

if __name__ == '__main__':
    process_stream()
from prometheus_api_client import PrometheusConnect
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway, write_to_textfile
import time
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
import pandas as pd
import warnings

# Suppress warnings from sklearn
warnings.filterwarnings("ignore", category=UserWarning)

# Config
PROMETHEUS_URL = "http://localhost:9090"
PUSHGATEWAY_URL = "http://localhost:9091"
METRIC_NAME = "up"
CONTAMINATION = 0.05  # 5% anomalies
QUERY_HOURS = 1  # Lookback time

# Step 1: Connect to Prometheus
print("[*] Connecting to Prometheus...")
prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)

# Step 2: Time window for query
end_time = datetime.now()
start_time = end_time - timedelta(hours=QUERY_HOURS)

# Step 3: Query metrics
print(f"[*] Querying metric '{METRIC_NAME}' from the last {QUERY_HOURS} hour(s)...")
try:
    metric_data = prom.get_metric_range_data(
        metric_name=METRIC_NAME,
        start_time=start_time,
        end_time=end_time,
        chunk_size=timedelta(minutes=15)
    )
except Exception as e:
    print(f"[!] Failed to fetch data from Prometheus: {e}")
    exit(1)

if not metric_data:
    print("[!] No data returned from Prometheus. Exiting.")
    exit(0)

# Step 4: Flatten data into DataFrame
rows = []
for series in metric_data:
    metric_labels = series['metric']
    for value_pair in series['values']:
        timestamp, value = value_pair
        try:
            rows.append({
                'timestamp': datetime.fromtimestamp(float(timestamp)),
                'value': float(value),
                **metric_labels
            })
        except ValueError:
            continue

df = pd.DataFrame(rows)
if df.empty:
    print("[!] No valid data points after flattening. Exiting.")
    exit(0)

df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)

# Step 5: Detect anomalies using Isolation Forest
print("[*] Running Isolation Forest anomaly detection...")
model = IsolationForest(contamination=CONTAMINATION)
df['score'] = model.fit_predict(df[['value']])
anomalies = df[df['score'] == -1]

# Step 6: Push anomaly result to PushGateway
registry = CollectorRegistry()
anomaly_gauge = Gauge('ai_anomaly_detected', 'AI Detected Anomaly', ['metric'], registry=registry)

if not anomalies.empty:
    print(f"[!] Detected {len(anomalies)} anomalies.")
    anomaly_gauge.labels(METRIC_NAME).set(1)

    detailed_registry = CollectorRegistry()

    for idx, row in anomalies.iterrows():
        anomaly_event_gauge = Gauge(
            'ai_anomaly_event',
            'Detailed anomaly event',
            ['metric', 'timestamp', 'value'],
            registry=detailed_registry
        )
        anomaly_event_gauge.labels(
            METRIC_NAME,
            idx.strftime("%Y-%m-%dT%H:%M:%S"),
            str(row['value'])
        ).set(1)

    try:
        push_to_gateway(PUSHGATEWAY_URL, job="ai-anomaly-events", registry=detailed_registry)
        print(f"[✓] {len(anomalies)} detailed anomaly records pushed.")
    except Exception as e:
        print(f"[!] Failed to push detailed events: {e}")

else:
    print("[✓] No anomalies detected.")
    anomaly_gauge.labels(METRIC_NAME).set(0)

try:
    push_to_gateway(PUSHGATEWAY_URL, job="ai-anomaly-job", registry=registry)
    print("[✓] Summary result pushed to PushGateway successfully.")
except Exception as e:
    print(f"[!] Failed to push to PushGateway: {e}")
    exit(1)
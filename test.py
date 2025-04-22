from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from datetime import datetime

registry = CollectorRegistry()
g = Gauge('ai_anomaly_event', 'Test Anomaly Event', ['metric', 'timestamp', 'value'], registry=registry)
g.labels('up', datetime.now().isoformat(), '0.0').set(1)

push_to_gateway('http://localhost:9091', job='ai-anomaly-events', registry=registry)

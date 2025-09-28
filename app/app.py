from flask import Flask, Response, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
import random

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "hwmonitor_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"]
)
REQUEST_LATENCY = Histogram(
    "hwmonitor_request_latency_seconds",
    "Request latency",
    ["endpoint"]
)

@app.before_request
def _start_timer():
    # record a start time for latency calculation per request (simple approach)
    setattr(app, "_start_time", time.time())

@app.after_request
def _record_metrics(response):
    # record counters and latency
    try:
        endpoint = getattr(app.view_functions.get(request.endpoint, None), "__name__", "unknown")
    except Exception:
        endpoint = "unknown"

    # method & status
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.path,
        http_status=response.status_code
    ).inc()

    # latency
    try:
        elapsed = time.time() - getattr(app, "_start_time", time.time())
    except Exception:
        elapsed = 0.0
    REQUEST_LATENCY.labels(endpoint=request.path).observe(elapsed)

    return response

@app.route("/")
def index():
    # Simulate a small random delay to make latency metric non-zero
    time.sleep(random.uniform(0.01, 0.2))
    return jsonify({"message": "Hello from HWMonitor Flask app!"})

@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# Needed for request/response objects in after_request
from flask import request

if __name__ == "__main__":
    # Bind to 0.0.0.0 for Kubernetes container networking
    app.run(host="0.0.0.0", port=8000)

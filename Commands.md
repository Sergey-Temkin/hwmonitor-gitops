## 1. Set Up Minikube Cluster
```bash
minikube start -p HWMonitor --driver=docker --cpus=2 --memory=2200 --disk-size=10g
kubectl config use-context HWMonitor
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A
minikube -p HWMonitor addons enable metrics-server
kubectl -n kube-system get pods | grep metrics-server
minikube -p HWMonitor ip
```


## Task 2 — Deploy Python Web Application:
### 2.1 Create folders:
```bash
mkdir -p app k8s k8s/monitoring argocd
ls -la
```
### 2.2 Create the Python app:
```bash
cat > app/app.py << 'EOF'
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
EOF
```
```bash
cat > app/requirements.txt << 'EOF'
flask==3.0.3
prometheus_client==0.20.0
gunicorn==22.0.0
EOF
```
### 2.3 Build the Docker image inside Minikube’s Docker:
```bash
cat > app/Dockerfile << 'EOF'
# Small, recent Python image
FROM python:3.12-slim

# Do not buffer Python output (good for logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS deps (if any) then Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# Expose the app port
EXPOSE 8000

# Simple command (Flask dev server is ok for lab)
CMD ["python", "app.py"]
# For production-like serving, consider:
# CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
EOF
```
### 2.4 Kubernetes manifests:
```bash
cat > k8s/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hwmonitor-web
  labels:
    app: hwmonitor-web
spec:
  replicas: 1  # For lab; can scale later
  selector:
    matchLabels:
      app: hwmonitor-web
  template:
    metadata:
      labels:
        app: hwmonitor-web
    spec:
      containers:
        - name: hwmonitor-web
          image: hwmonitor-web:1.0  # Local image built into Minikube's Docker
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          # Liveness & readiness use /healthz
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
            timeoutSeconds: 2
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 2
          # Small resources to fit your cluster limits
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "256Mi"
EOF
```
```bash
cat > k8s/service.yaml << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: hwmonitor-web
  labels:
    app: hwmonitor-web
spec:
  type: ClusterIP  # We'll port-forward; can switch to NodePort if you prefer
  selector:
    app: hwmonitor-web
  ports:
    - name: http
      port: 8000        # Service port inside the cluster
      targetPort: 8000  # Container port
EOF
```
### 2.5 Apply manifests:
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```
- Watch rollout:
```bash
kubectl rollout status deploy/hwmonitor-web
kubectl get pods -o wide
kubectl get svc
```
### 2.6 — Test the app:
```bash
kubectl port-forward svc/hwmonitor-web 8000:8000
```
### Open a second terminal:
- Test root:
```bash
http://127.0.0.1:8000/
```
- Test health:
```bash
curl -s http://127.0.0.1:8000/healthz
```
- Test metrics:
```bash
curl -s http://127.0.0.1:8000/metrics | head -n 20
```


## Task 3 — Deploy Prometheus & Grafana
### 3.1 — Add Helm repo & update:
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm search repo prometheus-community/kube-prometheus-stack
```
### 3.2 — Create a tuned values file:
```bash
cat > k8s/monitoring/values-prom.yaml << 'EOF'
# Namespace note: we'll install into "monitoring"
# Lightweight tuning for Minikube (2 CPU / 2.2GB RAM)

# -- Disable etcd scraping to avoid TLS/cert issues on Minikube
kubeEtcd:
  enabled: false

# -- Reduce scrape targets a bit (these are fine to keep enabled)
kubeControllerManager:
  enabled: true
kubeScheduler:
  enabled: true
kubeProxy:
  enabled: true
kubeStateMetrics:
  enabled: true
nodeExporter:
  enabled: true
prometheusOperator:
  enabled: true

# -- Prometheus settings
prometheus:
  prometheusSpec:
    retention: 24h
    scrapeInterval: 30s
    evaluationInterval: 30s
    resources:
      requests:
        cpu: 100m
        memory: 256Mi
      limits:
        cpu: 500m
        memory: 512Mi
  service:
    type: ClusterIP
  # Disable PVCs for homework (ephemeral)
  prometheusSpecExternalLabels: {}
  thanos: null

# -- Alertmanager settings
alertmanager:
  alertmanagerSpec:
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
      limits:
        cpu: 200m
        memory: 128Mi
  service:
    type: ClusterIP

# -- Grafana settings (default admin: admin / see password below)
grafana:
  adminPassword: "Prom-Admin123!"
  service:
    type: ClusterIP
  resources:
    requests:
      cpu: 50m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 256Mi
  # Import nothing by default; we'll make a small dashboard in Task 4
  defaultDashboardsEnabled: true

# -- Disable persistent volumes to reduce footprint (ephemeral pods)
prometheusOperator:
  admissionWebhooks:
    patch:
      enabled: true

# -- Reduce replica counts to 1 (defaults are already 1)
EOF
```
### 3.3 — Create the namespace and install the chart:
```bash
kubectl create namespace monitoring
helm install prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f k8s/monitoring/values-prom.yaml
```
### 3.4 — Verify all pods are healthy:
```bash
kubectl get pods -n monitoring
kubectl get svc  -n monitoring
kubectl get crds | grep monitoring.coreos.com | wc -l
```
### 3.5 — Port-forward Prometheus & Grafana:
- Prometheus:
```bash
kubectl port-forward -n monitoring svc/prometheus-stack-kube-prom-prometheus 9090:9090
```
- Grafana:
```bash
kubectl port-forward -n monitoring svc/prometheus-stack-grafana 3000:80
```
- See services:
```bash
kubectl get svc -n monitoring
```
### Login in Browser:
- Prometheus:  
http://127.0.0.1:9090
- Grafana:  
http://127.0.0.1:3000
- Login for Grafana:
```bash
user: admin
pass: Prom-Admin123!
```

## Set Up Monitoring and Alerts
### 4.1 ServiceMonitor for the Python app:
```bash
cat > k8s/monitoring/servicemonitor-hwmonitor.yaml << 'EOF'
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hwmonitor-web
  namespace: monitoring
  labels:
    # Important: This matches the kube-prometheus-stack's selector so it picks up this ServiceMonitor
    release: prometheus-stack
spec:
  # We want to scrape the Service that lives in the "default" namespace
  namespaceSelector:
    matchNames:
      - default
  # Match the Service by its metadata.labels (Service has app: hwmonitor-web)
  selector:
    matchLabels:
      app: hwmonitor-web
  endpoints:
    - port: http        # must match the Service's port name
      path: /metrics    # our Flask app's metrics endpoint
      interval: 15s
      scheme: http
EOF
```
```bash
kubectl apply -f k8s/monitoring/servicemonitor-hwmonitor.yaml
kubectl get servicemonitors.monitoring.coreos.com -n monitoring
```
### 4.2 Alert rule: restarts > 1 in 5 minutes:
```bash
cat > k8s/monitoring/alertrule-hwmonitor.yaml << 'EOF'
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hwmonitor-alerts
  namespace: monitoring
  labels:
    # Important: so kube-prometheus-stack Prometheus selects these rules
    release: prometheus-stack
spec:
  groups:
    - name: hwmonitor.rules
      rules:
        - alert: HWMonitorAppHighRestarts
          # More than 1 restart in the last 5 minutes for our container
          expr: increase(kube_pod_container_status_restarts_total{namespace="default",container="hwmonitor-web"}[5m]) > 1
          for: 0m
          labels:
            severity: warning
            app: hwmonitor-web
          annotations:
            summary: "hwmonitor-web restarting frequently"
            description: "Container restarted more than once in 5 minutes (value={{ $value }})."
EOF
```
```bash
kubectl apply -f k8s/monitoring/alertrule-hwmonitor.yaml
kubectl get prometheusrules.monitoring.coreos.com -n monitoring | grep hwmonitor
```
- Now open Prometheus → Alerts; you should see HWMonitorAppHighRestarts listed (likely in Inactive state until there are >1 restarts in 5m).  
- Force restarts:
```bash
kubectl delete pod -l app=hwmonitor-web
```
### 4.3 Simple Grafana dashboard (auto-import via ConfigMap):
```bash
cat > k8s/monitoring/grafana-dashboard-hwmonitor.yaml << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-hwmonitor
  namespace: monitoring
  labels:
    grafana_dashboard: "1"  # <-- lets the Grafana sidecar auto-import it
data:
  hwmonitor-dashboard.json: |
    {
      "title": "HWMonitor - App Overview",
      "schemaVersion": 39,
      "style": "dark",
      "tags": ["hwmonitor"],
      "timezone": "",
      "time": {"from": "now-15m", "to": "now"},
      "panels": [
        {
          "type": "timeseries",
          "title": "Requests rate by endpoint (5m)",
          "gridPos": {"h": 9, "w": 24, "x": 0, "y": 0},
          "targets": [
            {
              "refId": "A",
              "expr": "rate(hwmonitor_requests_total[5m])",
              "legendFormat": "{{endpoint}}",
              "datasource": { "type": "prometheus", "uid": "prometheus" }
            }
          ],
          "options": { "legend": { "displayMode": "list", "placement": "bottom" } },
          "fieldConfig": { "defaults": {}, "overrides": [] }
        },
        {
          "type": "timeseries",
          "title": "Request latency p50 (5m)",
          "gridPos": {"h": 9, "w": 24, "x": 0, "y": 9},
          "targets": [
            {
              "refId": "B",
              "expr": "histogram_quantile(0.5, sum(rate(hwmonitor_request_latency_seconds_bucket[5m])) by (le))",
              "legendFormat": "p50 latency",
              "datasource": { "type": "prometheus", "uid": "prometheus" }
            }
          ],
          "fieldConfig": { "defaults": {}, "overrides": [] }
        }
      ],
      "templating": { "list": [] },
      "annotations": { "list": [] },
      "editable": true
    }
EOF
```
```bash
kubectl apply -f k8s/monitoring/grafana-dashboard-hwmonitor.yaml
```
- In Grafana → Dashboards, find “HWMonitor - App Overview”.
### 4.A — Verify the ServiceMonitor target is UP:
- Open http://127.0.0.1:9090 → Status → Targets and look for the target that scrapes the default namespace Service:"hwmonitor-web: (port name must be http).
- It should be UP within ~30s.
### 4.B — Trigger and see the alert (restarts > 1 in 5m):
- Force restarts quickly (then revert):
```bash
# Break liveness & speed it up
kubectl patch deploy hwmonitor-web --type='json' -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/does-not-exist"},
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/periodSeconds","value":5},
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/failureThreshold","value":1}
]'
```
```bash
# Wait for >= 2 restarts
kubectl get pod -l app=hwmonitor-web \
  -o=custom-columns=NAME:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount
```
```bash
# Revert probe to healthy
kubectl patch deploy hwmonitor-web --type='json' -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/healthz"},
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/periodSeconds","value":10},
  {"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/failureThreshold","value":3}
]'
```
- Open Prometheus → Alerts and confirm HWMonitorAppHighRestarts is Firing.
### 4.C — See your Grafana dashboard:
- If panels show “Data source not found”, edit the panel and set datasource to Prometheus.
- Generate a bit of traffic so graphs populate:
```bash
kubectl port-forward svc/hwmonitor-web 8000:8000
for i in {1..100}; do curl -s http://127.0.0.1:8000/ > /dev/null; done
```

## Set Up ArgoCD for GitOps
### 5.1 — Prepare a Git repo with only the app manifests:
- Create the GitOps folder and copy manifests:
```bash
mkdir -p gitops/app
cp k8s/deployment.yaml gitops/app/deployment.yaml
cp k8s/service.yaml    gitops/app/service.yaml
ls -la gitops/app
```
```bash
cat > gitops/README.md << 'EOF'
# HWMonitor GitOps (ArgoCD)
This folder contains only the Kubernetes manifests for the Python app (Deployment + Service).
ArgoCD watches this path and syncs the app to the cluster automatically.
EOF
```
```bash
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
.vscode/
.idea/
EOF
```
- Initialize a new repo and push to GitHub:
```bash
# Init and first commit
git init
git add gitops .gitignore
git commit -m "GitOps: app manifests for ArgoCD"

# Create a new public repo on your GitHub (change name if you prefer)
hwmonitor-gitops

# Add remote & push
git branch -M main
git remote add origin https://github.com/Sergey-Temkin/hwmonitor-gitops.git
git push -u origin main
```
### 5.2 — Install ArgoCD:
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```
- Watch pods until Ready
```bash
kubectl get pods -n argocd
# repeat until argocd-application-controller, argocd-repo-server, argocd-server, argocd-dex-server are Running/1/1
```
- Port-forward ArgoCD UI (keep this in its own terminal):
```bash
kubectl port-forward -n argocd svc/argocd-server 8080:443
```
- Get initial admin password:
```bash
kubectl get secret argocd-initial-admin-secret -n argocd -o \
jsonpath="{.data.password}" | base64 -d && echo
# Copy the password
```
- Open: https://localhost:8080
- Username: admin
- Password: copied password
### 5.4 — Create the ArgoCD Application:
```bash
cat > argocd/app-hwmonitor.yaml << 'EOF'
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: hwmonitor-app
  namespace: argocd
  labels:
    # Who owns this app
    app.kubernetes.io/part-of: hwmonitor
    app.kubernetes.io/managed-by: argocd
spec:
  # Use the default ArgoCD project
  project: default

  # --- Source: where to pull manifests from (your Git repo) ---
  source:
    repoURL: https://github.com/Sergey-Temkin/hwmonitor-gitops.git   # <-- your repo
    targetRevision: main                                             # branch or tag
    path: gitops/app                                                 # <-- only the app manifests (Deployment+Service)

  # --- Destination: where to apply them ---
  destination:
    server: https://kubernetes.default.svc                           # current cluster
    namespace: default                                               # app namespace

  # --- Sync policy: automated GitOps ---
  syncPolicy:
    automated:
      prune: true        # delete cluster objects removed from Git
      selfHeal: true     # fix drift if someone kubectl-ed different state
    syncOptions:
      - CreateNamespace=true  # harmless here (ns already exists)
EOF
```
```bash
kubectl apply -f argocd/app-hwmonitor.yaml
```
- Check Application status:
```bash
kubectl get applications -n argocd
argocd app get hwmonitor-app
```





#  Home Assignment: Kubernetes Monitoring & Continuous Deployment with ArgoCD
## Objective
- The goal of this assignment is to provide hands-on experience in:
1. Deploying a monitoring stack (Prometheus & Grafana) on a Kubernetes cluster.
2. Building and deploying a Python web application with Kubernetes.
3. Setting up alerts for application failures.
4. Implementing GitOps using ArgoCD for automated deployment.

## Assignment Tasks:

### Task 1: Set Up Minikube Cluster
- Start a Minikube cluster with sufficient resources:  
```bash
minikube start -p HWMonitor --driver=docker --cpus=2 --memory=2200 --disk-size=10g  
```
- Verify the cluster is running:
```bash
kubectl get nodes
```

### Task 2: Deploy Python Web Application:
1. Clone the provided repository containing the Python application and Kubernetes manifests.
2. Build a Docker image for the Python app and push it to a container registry or use Minikube's local Docker registry.  
- Deploy the application using the provided Kubernetes manifests (deployment.yaml and service.yaml):
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```
3. Verify the deployment:
```bash
kubectl get pods
kubectl get svc
```

### Task 3: Deploy Prometheus & Grafana Stack:
1. Add the Prometheus Helm chart repository:
```bash
helm repo add prometheus-community
https://prometheus-community.github.io/helm-charts
helm repo update
```
2. Install Prometheus and Grafana using Helm:
```bash
helm install prometheus-stack
prometheus-community/kube-prometheus-stack
```
3. Verify the installation:
```bash
kubectl get pods -n default
```

### Task 4: Set Up Monitoring and Alerts:
1. Create a ServiceMonitor to monitor the Python application.
2. Define an alert rule that triggers when the Python application restarts or fails more than
once in a 5-minute interval.
3. Apply the alert rule to Prometheus.
4. Access Prometheus and Grafana UIs by forwarding their ports:
```bash
kubectl port-forward svc/prometheus-stack-kube-prometheus-prometheus 9090:9090
kubectl port-forward svc/prometheus-stack-grafana 3000:80
```
5. Create a simple Grafana dashboard to visualize the Python app's metrics.

### Task 5: Set Up ArgoCD for GitOps:
1. Install ArgoCD:
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f
https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/in
stall.yaml
```
- Forward the ArgoCD server port and access the UI:
```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```
2. Access ArgoCD at https://localhost:8080.
```bash
argocd login localhost:8080 --username admin --password <initial-password>
```
- Retrieve the initial password:
```bash
kubectl get secret argocd-initial-admin-secret -n argocd -o
jsonpath="{.data.password}" | base64 -d
```
4. Create a GitOps workflow:  
- Connect ArgoCD to your Git repository.   
- Create an ArgoCD Application that syncs the Kubernetes manifests for the Python app automatically.

### Deliverables
1. A running Minikube cluster with:
- Python application deployed and running.
- Prometheus & Grafana stack deployed and configured.
- Alerts set up for application restarts/failures.
2. Screenshots showing:
- Prometheus alert triggering when the Python app restarts.
- Grafana dashboard displaying Python app metrics.
- ArgoCD UI showing synchronized deployment.
3. A brief report including:
- Steps you followed to complete the assignment.
- Challenges faced and how you overcame them.
- Lessons learned from the assignment.

### Submission Guidelines
- Submit a zip file containing:
1. The Kubernetes manifests used.
2. Screenshots as mentioned in the deliverables.
3. The brief report.
- Ensure all resources are documented properly.
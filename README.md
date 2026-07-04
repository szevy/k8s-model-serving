# Model Serving on Kubernetes

A hands-on project demonstrating how to containerise a model inference service and deploy it to a Kubernetes cluster with production-oriented patterns: health probes, resource management, and horizontal autoscaling.

## Overview

This project packages a simple FastAPI inference service into a Docker image and deploys it to a local Kubernetes cluster (minikube). It demonstrates the core Kubernetes workflow used to serve ML models in production, on a local single-node cluster.

## Architecture

```
Client request
      |
      v
  Service (NodePort)         <- stable network endpoint
      |
      v
  Deployment                 <- manages pods, maintains desired state
      |
      v
  Pod(s) running the container
      |
      v
  FastAPI app (/health, /predict)
```

- **FastAPI service** exposes a `/health` endpoint (for probes) and a `/predict` endpoint (inference).
- **Docker image** packages the app and its dependencies.
- **Kubernetes Deployment** manages the pods and maintains the desired replica count.
- **Kubernetes Service** (NodePort) provides a stable endpoint to reach the pods.
- **Horizontal Pod Autoscaler (HPA)** automatically scales pods based on CPU utilisation.

## Project Structure

```
.
├── README.md
├── app/                    # Application code
│   ├── app.py              # FastAPI inference service
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile          # Container image definition
└── k8s/                    # Kubernetes manifests
    ├── deployment.yaml     # Deployment (health probes, resource limits)
    └── service.yaml        # Service (NodePort)
```

## Key Kubernetes Features Demonstrated

- **Deployment and Service manifests** (declarative configuration)
- **Liveness and readiness probes** (self-healing and traffic management via `/health`)
- **Resource requests and limits** (CPU/memory allocation)
- **Horizontal Pod Autoscaling** (automatic scaling based on CPU)
- **Rolling updates** (zero-downtime deployment on manifest changes)

## Prerequisites

- Docker
- kubectl
- minikube

## How to Run

1. **Start the cluster**
   ```bash
   minikube start --driver=docker
   ```

2. **Build the image** (from the `app/` directory)
   ```bash
   docker build -t model-service:latest ./app
   ```

3. **Load the image into minikube**
   ```bash
   minikube image load model-service:latest
   ```

4. **Deploy**
   ```bash
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   ```

5. **Check it's running**
   ```bash
   kubectl get pods
   ```

6. **Enable autoscaling** (requires metrics-server)
   ```bash
   minikube addons enable metrics-server
   kubectl autoscale deployment model-service --cpu=50% --min=1 --max=5
   kubectl get hpa
   ```

7. **Test the endpoints**
   ```bash
   minikube service model-service --url
   # then, using the URL returned:
   curl <url>/health
   curl -X POST <url>/predict -H "Content-Type: application/json" -d '{"x": 5}'
   ```

## Endpoints

- `GET /health` - health check (returns `{"status": "ok"}`)
- `POST /predict` - inference (accepts `{"x": <number>}`, returns `{"prediction": <result>}`)

## Notes

This project runs on a local single-node cluster (minikube) for learning and demonstration. The same manifests and patterns apply to managed Kubernetes services (EKS, GKE) with adjustments for cloud load balancers, storage, and multi-node scheduling.
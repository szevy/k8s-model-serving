# Model Serving on Kubernetes

A hands-on project demonstrating how to containerise a machine learning inference service and deploy it to Kubernetes, with health probes, resource management, horizontal autoscaling, and a documented debugging workflow. Runs locally on minikube at zero cost.

## Overview

This project packages a FastAPI model-inference service as a container image and deploys it to a local Kubernetes cluster. It demonstrates the core Kubernetes serving workflow end to end: Deployment, Service, health probes, resource requests and limits, and a Horizontal Pod Autoscaler, plus a practical debugging workflow for diagnosing common failures.

## Architecture

- **FastAPI service** (`app/app.py`) exposing `/health` (for probes) and `/predict` (inference) endpoints.
- **Deployment** managing replicas, with liveness and readiness probes and resource requests/limits.
- **Service** (NodePort) exposing the pods behind a stable endpoint.
- **HorizontalPodAutoscaler** scaling replicas based on CPU utilisation.

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
    ├── service.yaml        # Service (NodePort)
    └── hpa.yaml            # Horizontal Pod Autoscaler
```

## Prerequisites

- Docker
- minikube
- kubectl
- metrics-server (required for the Horizontal Pod Autoscaler; see step 1 below)

## Quick Start

1. **Start the cluster and enable metrics-server**
   ```bash
   minikube start
   minikube addons enable metrics-server
   ```
   The HorizontalPodAutoscaler needs metrics-server to read CPU utilisation; without it the HPA cannot scale and its TARGETS will show `<unknown>`.

2. **Build the image**
   ```bash
   docker build -t model-service:latest ./app
   ```

3. **Load the image into minikube**

   The deployment uses `imagePullPolicy: Never` with a local image, so the image must be loaded into the cluster's image store (it is not pulled from a registry):
   ```bash
   minikube image load model-service:latest
   minikube image ls | grep model      # confirm it is present
   ```
   Note: after `minikube delete`, the cluster's image store is wiped, so the image must be re-loaded (not rebuilt, unless the code changed).

4. **Deploy**
   ```bash
   kubectl apply -f k8s/
   kubectl get pods                     # wait for pods to become 1/1 Running
   ```

5. **Test the service**
   ```bash
   kubectl port-forward service/model-service 8000:8000
   # in another terminal:
   curl http://localhost:8000/health
   curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d '{"x": 5}'
   ```
   Expected responses: `{"status":"ok"}` from `/health`, and `{"prediction":10.0}` from `/predict` (the service returns `x * 2`). The interactive API docs are also available at `http://localhost:8000/docs`.

6. **Clean up**
   ```bash
   minikube delete
   ```

## Key Concepts Demonstrated

- **Deployment and replicas** managing the desired number of pods and keeping them healthy.
- **Service (NodePort)** providing a stable network endpoint that load-balances across pods.
- **Liveness probe** telling Kubernetes whether to restart a stuck container (checks `/health`).
- **Readiness probe** telling Kubernetes whether the pod is ready to receive traffic; a pod that fails readiness is held out of the Service's load balancing until it recovers.
- **Resource requests and limits** requests for scheduling (100m CPU / 128Mi), limits as a ceiling (500m CPU / 256Mi).
- **Horizontal Pod Autoscaler** scaling pods based on CPU (min 3, max 5, target 50% CPU); requires metrics-server (`minikube addons enable metrics-server`). If TARGETS shows `<unknown>` in `kubectl get hpa`, metrics-server is not running.

## Debugging and Observability

Practical commands for inspecting and debugging the service.

### Viewing logs

```bash
kubectl logs <pod-name>                  # a pod's logs
kubectl logs <pod-name> -f               # follow / stream live
kubectl logs <pod-name> --previous       # logs from a crashed (previous) container
kubectl logs -l app=model-service        # logs across all pods via label
```

### Inspecting state

```bash
kubectl get pods                         # STATUS and READY columns
kubectl describe pod <pod-name>          # Events section shows the cause of failures
kubectl get events --sort-by=.metadata.creationTimestamp
kubectl get endpoints model-service      # is the Service wired to pods?
kubectl rollout status deployment/model-service
```

### Worked debugging examples

Two common failures were reproduced and diagnosed on this deployment:

**1. Bad image (`ErrImageNeverPull`)**

Setting a nonexistent image tag causes the new pod to fail:
```bash
kubectl set image deployment/model-service model-service=model-service:doesnotexist
kubectl get pods                         # new pod: ErrImageNeverPull, 0/1
kubectl describe pod <failing-pod>       # Events: image not present with pull policy Never
kubectl rollout undo deployment/model-service   # revert to the working revision
```
Because `imagePullPolicy: Never` is set (correct for local images), a missing image produces `ErrImageNeverPull` rather than `ImagePullBackOff`, Kubernetes cannot fall back to pulling from a registry. The rolling update keeps the existing healthy pods serving throughout, since new pods are only swapped in once healthy.

**2. Failing readiness probe (`Running` but `0/1 Ready`)**

Pointing the readiness probe at a nonexistent path makes the pod run but never become ready:
```bash
kubectl patch deployment model-service --type='json' \
  -p='[{"op":"replace","path":"/spec/template/spec/containers/0/readinessProbe/httpGet/path","value":"/wrongpath"}]'
kubectl get pods                         # Running but 0/1 READY
kubectl describe pod <pod-name>          # Events: Readiness probe failed, HTTP statuscode 404
kubectl logs <pod-name>                  # app is healthy: the issue is the probe, not the app
kubectl apply -f k8s/                    # fix declaratively by re-applying the correct manifest
```
The pod stays `Running` (the container and app are fine) but `Ready: False`, so it is removed from the Service's load balancing. The liveness probe still passes (correct path), so the pod is held out of traffic but not restarted, illustrating the difference between readiness (should I get traffic?) and liveness (should I be restarted?).

### Rollout history and rollback

```bash
kubectl rollout history deployment/model-service        # list revisions
kubectl rollout undo deployment/model-service           # revert the last change
kubectl rollout undo deployment/model-service --to-revision=2   # revert to a specific revision
```

### Checking the autoscaler

```bash
kubectl get hpa                          # REPLICAS and TARGETS (e.g. 1%/50%)
```
If TARGETS shows `<unknown>`, the HPA cannot read CPU metrics, enable metrics-server with `minikube addons enable metrics-server` and wait about a minute. Note that Kubernetes is eventually consistent: immediately after a rollout the replica count may briefly differ from the HPA minimum while pods churn, then converge back to the configured minimum.

## Notes

This is a foundational, hands-on project run locally on minikube. The concepts and manifests carry across to managed Kubernetes (EKS, GKE), which add cloud load balancers, storage classes, and multi-node scheduling. The debugging workflow above (get, describe, logs, events) is the same on any cluster.
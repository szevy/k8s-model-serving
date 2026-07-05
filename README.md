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
    ├── deployment.yaml     # Deployment (health probes, resource limits, config/secret injection)
    ├── service.yaml        # Service (NodePort)
    ├── hpa.yaml            # Horizontal Pod Autoscaler
    ├── configmap.yaml      # Non-sensitive configuration
    ├── secret.example.yaml # Secret template (placeholder value; copy to secret.yaml, which is gitignored)
    ├── job.yaml            # Run-to-completion batch Job example
    ├── cronjob.yaml        # Scheduled CronJob example
    └── ingress.yaml        # Ingress (HTTP routing by hostname/path)
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

   Create your real secret from the template first (this file is gitignored, never commit real secret values):
   ```bash
   cp k8s/secret.example.yaml k8s/secret.yaml    # then edit the value in secret.yaml
   ```
   Then apply everything:
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

## Configuration: ConfigMaps and Secrets

Application configuration is externalised from the container image into the cluster, so it can change without rebuilding the image. The deployment injects these as environment variables via `envFrom`.

- **ConfigMap** (`configmap.yaml`) holds non-sensitive config (`MODEL_NAME`, `LOG_LEVEL`). Safe to commit.
- **Secret** (`secret.example.yaml`) is a template with a placeholder. Copy it to `secret.yaml`, set a real value, and keep `secret.yaml` out of git (it is gitignored). Kubernetes Secrets are only base64-encoded, not encrypted, so real secret values must never be committed; for production use a secrets manager or sealed-secrets.

```bash
kubectl apply -f k8s/configmap.yaml
cp k8s/secret.example.yaml k8s/secret.yaml   # then edit the value
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml         # references both via envFrom

# verify the values are injected into the running container
kubectl exec <pod-name> -- env | grep -E "MODEL_NAME|LOG_LEVEL|API_KEY"
```

Note: changing a ConfigMap or Secret does not automatically update running pods, environment variables are read at pod creation. After changing config, restart the pods to pick up the new values:

```bash
kubectl rollout restart deployment/model-service
```

## Batch Workloads: Jobs and CronJobs

Not every workload is a long-running service. Jobs and CronJobs handle run-to-completion and scheduled tasks (in ML: one-off training runs, batch inference, scheduled retraining).

- **Job** (`job.yaml`) runs a pod to completion, then stops. A completed Job pod shows `STATUS Completed` with `READY 0/1`, this is success, not failure: the READY column counts running containers, and a Job's container exits when done. This is the key difference from a Deployment, which stays `1/1 Running`.
- **CronJob** (`cronjob.yaml`) spawns a Job on a cron schedule (`*/1 * * * *` = every minute). It is the Kubernetes-native equivalent of an external scheduler.

```bash
kubectl apply -f k8s/job.yaml
kubectl get pods                     # demo-job pod: Running, then Completed
kubectl logs job/demo-job

kubectl apply -f k8s/cronjob.yaml
kubectl get cronjobs
kubectl get jobs                     # after ~1 min, the CronJob has spawned Job(s)

# clean up when done (a CronJob keeps spawning jobs every minute otherwise)
kubectl delete cronjob demo-cronjob
kubectl delete job demo-job
```

## External Access: Ingress

The service can be exposed via an Ingress, which provides HTTP routing by hostname and path, one entry point routing to the right Service (a cleaner alternative to a NodePort or a load balancer per service). Ingress is two parts: the Ingress resource (the routing rules, in `ingress.yaml`) and an ingress controller (the engine that enforces them, here nginx).

The routing chain is Ingress -> Service -> Pod: the Ingress picks the Service by host/path, and the Service load-balances across that app's pods.

```bash
minikube addons enable ingress               # install the nginx ingress controller
kubectl get pods -n ingress-nginx            # wait for the controller pod to be Running
kubectl apply -f k8s/ingress.yaml
kubectl get ingress                          # ADDRESS appears after ~30-60s
```

Testing on the minikube Docker driver (WSL): the ingress IP (e.g. 192.168.49.2) is inside the Docker network and not directly routable from the host. Reach the service through the controller with a port-forward:

```bash
kubectl port-forward -n ingress-nginx service/ingress-nginx-controller 8080:80
# in another terminal:
curl -H "Host: model-service.local" http://localhost:8080/health   # {"status":"ok"}
```

The `Host` header must match the Ingress rule's host (`model-service.local`), that is how the Ingress selects the routing rule. On a managed cluster (EKS, GKE) the Ingress receives a real external load-balancer IP and is directly reachable; the port-forward is only needed because of the local Docker driver's network isolation.

## Multi-Node Scheduling and Resilience

The manifests also work on a multi-node cluster, which demonstrates pod distribution, self-healing, and scheduling control.

```bash
minikube start --nodes 3                 # a 3-node cluster (1 control plane + 2 workers)
kubectl get nodes                        # minikube, minikube-m02, minikube-m03
minikube image load model-service:latest
kubectl apply -f k8s/
kubectl get pods -o wide                 # the NODE column shows pod placement across nodes
```

**Self-healing on node failure.** Draining a node evicts its pods; Kubernetes reschedules them onto healthy nodes to maintain the desired replica count, so the service stays up:

```bash
kubectl drain minikube-m02 --ignore-daemonsets --delete-emptydir-data
kubectl get pods -o wide                 # evicted pod reappears on another node
kubectl get nodes                        # minikube-m02: Ready,SchedulingDisabled
kubectl uncordon minikube-m02            # return the node to the schedulable pool
```

**Even spreading with pod anti-affinity.** By default the scheduler does not spread replicas perfectly evenly. The deployment includes a pod anti-affinity rule (`topologyKey: kubernetes.io/hostname`) that prefers to place each `model-service` pod on a different node, maximising resilience (losing one node loses only one replica). It uses the soft form (`preferredDuringSchedulingIgnoredDuringExecution`), which prefers spreading but still schedules if it cannot; the hard form (`requiredDuringScheduling...`) would leave pods Pending if the spread cannot be satisfied.

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
kubectl get endpointslices -l kubernetes.io/service-name=model-service   # pod IPs the Service routes to
# older equivalent: kubectl get endpoints model-service (deprecated in v1.33+)
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

**3. CrashLoopBackOff (container crashes on startup)**

A container that exits with an error on startup is restarted repeatedly, entering CrashLoopBackOff:
```bash
kubectl get pods                         # STATUS CrashLoopBackOff, RESTARTS climbing
kubectl describe pod <pod-name>          # Last State: Terminated, Exit Code: 1
kubectl logs <pod-name> --previous       # the crashed container's output (the crash reason)
```
The key signature is a climbing RESTARTS count. `describe` shows `Last State: Terminated` with the exit code, confirming the container ran and died (not an image or scheduling problem). `kubectl logs --previous` is essential here: the current container is a fresh restart, so the reason it died is in the previous instance. On a healthy pod (RESTARTS 0) `--previous` returns "not found", it only has output when a container has actually crashed.

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
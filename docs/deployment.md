# Deployment and Operations

## Local development

1. Install Docker Desktop with Compose and Python 3.11 or newer.
2. Copy `.env.example` to `.env`; replace `PII_HMAC_KEY` with at least 32 random characters.
3. Run `docker compose up --build`.
4. Wait for API health at `http://localhost:8000/health/ready`.
5. Submit the README sample event, then query recommendations.
6. Stop with `Ctrl+C`; Compose volumes preserve local Redis state and event archives.

The local broker and Redis are intentionally unauthenticated only on a private Compose network. Do not expose this topology as a public service.

## Azure AKS deployment

This project includes a Bicep deployment for a student-scale AKS environment. It creates AKS, Azure Container Registry, Event Hubs, Blob Storage, Key Vault, managed identities, and scoped data-plane role assignments. Redis is a single-replica, private in-cluster service for the demonstration; its `emptyDir` data is disposable and can be rebuilt by replaying retained events. The API currently uses a temporary public HTTP load balancer for the presentation; do not use real personal data or production credentials.

The demonstrated deployment target is subscription `f6dd9f15-cc54-428c-85cb-160f40cd7da3`, region `eastus`, and resource group `test`. A temporary public HTTP load balancer is currently enabled for the student presentation at `http://48.194.77.114`. It is not production-safe: bearer tokens are not encrypted in transit. Remove the public exposure after the demo.

1. Sign in and create the resource group:

   ```powershell
   az login
   az account set --subscription f6dd9f15-cc54-428c-85cb-160f40cd7da3
   $operatorId = az ad signed-in-user show --query id -o tsv
   az group create --name test --location eastus
   ```

2. Preview the infrastructure, inspect every resource and role assignment, then deploy only if the preview matches the intended scope:

   ```powershell
   az deployment group what-if --name streamify-preview --resource-group test `
     --template-file infra/main.bicep --parameters "@infra/main.parameters.json" "deploymentPrincipalId=$operatorId"
   az deployment group create --name streamify-deploy --resource-group test `
     --template-file infra/main.bicep --parameters "@infra/main.parameters.json" "deploymentPrincipalId=$operatorId"
   ```

   The template uses two fixed `Standard_D2as_v7` AKS nodes because the subscription currently has only four regional vCPUs available; the original three-node plan requires six. This reduced-size student demo has less node-failure tolerance and is not a production high-availability setup. It also creates a four-partition Event Hub, seven-day retention, a Basic ACR, and an LRS storage account. It enables OIDC/workload identity and managed Entra ID with Azure RBAC, disables local AKS accounts, Storage shared-key auth, and Event Hubs local auth, and enables Key Vault purge protection. The deployment operator receives AKS cluster-admin access at the cluster scope. The API has Event Hubs Data Sender; the worker has Event Hubs Data Receiver and Blob Data Contributor; only the AKS CSI add-on identity receives Key Vault Secrets User.

3. Build and push both images. In this subscription ACR Tasks are not permitted, so use a local Docker daemon:

   ```powershell
   $outputs = (az deployment group show --name streamify-deploy --resource-group test `
     --query properties.outputs -o json | ConvertFrom-Json)
   $acr = $outputs.acrName.value
   $loginServer = az acr show --name $acr --query loginServer -o tsv
   az acr login --name $acr
   docker build --file Dockerfile --tag "$loginServer/streamify-api:1.0.1" .
   docker push "$loginServer/streamify-api:1.0.1"
   docker build --file Dockerfile.worker --tag "$loginServer/streamify-worker:1.0.1" .
   docker push "$loginServer/streamify-worker:1.0.1"
   ```

4. Generate separate 256-bit read/write tokens, an HMAC key, and a Redis password. Store them in the provisioned Key Vault as `api-read-token`, `api-write-token`, `pii-hmac-key`, `redis-password`, and `redis-url`. Grant the deployment operator a temporary Key Vault Secrets Officer role only if needed to seed these values, then remove that assignment. Never place secret values in source files, deployment parameters, or a committed Kubernetes Secret.

5. Fetch AKS credentials, install `kubelogin` if needed, and materialize the Kubernetes template using deployment outputs:

   ```powershell
   az aks get-credentials --resource-group test --name $outputs.aksName.value
   az aks install-cli
   ```

   Replace each `REPLACE_WITH_*` token in `deploy/kubernetes/streamify.yaml` with its matching output: ACR login server, Event Hub namespace/topic names, storage account/container, Key Vault name, tenant ID, API and worker identity client IDs, and Key Vault CSI add-on client ID. Keep the rendered file private and ephemeral. Apply it and wait for readiness:

   ```powershell
   kubectl apply -f <rendered-manifest-path>
   kubectl -n streamify rollout status deployment/streamify-redis
   kubectl -n streamify rollout status deployment/streamify-api
   kubectl -n streamify rollout status deployment/streamify-worker
   kubectl -n streamify get pods,services,hpa
   ```

6. For a short-lived student presentation, the API Service may be changed to `LoadBalancer` to obtain a public HTTP address. HTTP does not encrypt bearer tokens: use demo-only credentials, never send real personal data, and change the Service back to `ClusterIP` after the presentation. For normal/private operation, keep it internal and use a port-forward:

   ```powershell
   kubectl -n streamify port-forward service/streamify-api 8000:80
   ```

   For private operation, in another terminal call `/health/ready` and submit a sample event using the generated write token; then query recommendations using the separate read token. Check pod logs, Event Hubs consumer lag, and the Blob archive before declaring the deployment healthy. When temporarily public, get the address with `kubectl -n streamify get service streamify-api`; the API docs are at `http://<EXTERNAL-IP>/docs`.

The Kubernetes HPA is capped at six API pods and four workers. The worker limit matches the four stream partitions; the cluster has a fixed two-node pool and no node autoscaler. Request additional Azure regional vCPU quota before scaling the node pool or claiming production availability. Redis traffic inside the cluster is authenticated but not TLS-encrypted; use a TLS-enabled managed Redis service and private endpoints for production. Do not expose the API without a real TLS ingress, per-user authentication, and production network controls.

### Event Hubs Kafka OAuth

Set `EVENTHUB_NAMESPACE` to the namespace name (without `.servicebus.windows.net`). The client uses SASL_SSL and OAUTHBEARER, requesting an Azure Identity token for `https://<namespace>.servicebus.windows.net/.default`. `KAFKA_BOOTSTRAP_SERVERS` is retained for local Kafka-compatible development; the client derives the cloud endpoint from the namespace. Pre-create the two Event Hubs as above: the application intentionally does not attempt Kafka topic creation against the managed cloud endpoint.

### API access control

`POST /v1/events` requires the write-scope bearer token; `GET /v1/recommendations` requires the separate read-scope token. Generate high-entropy values of at least 32 characters and send them in the `Authorization: Bearer ...` header. These are shared prototype credentials, not individual user identities. Replace them with an Entra ID/OAuth JWT validation and per-user policy before production.

### Blob configuration

Set `AZURE_STORAGE_ACCOUNT_URL` to `https://<account>.blob.core.windows.net` and `AZURE_STORAGE_CONTAINER` to the provisioned container. Azure SDK `DefaultAzureCredential` uses AKS workload identity; no account key is required.

## Operations and maintenance

- Monitor API p95/p99 latency, accepted/failed event counters, pod saturation, consumer-group lag, DLQ rate, Redis memory, Blob errors, and Event Hubs throttling.
- Scale API replicas independently; scale workers only up to the number of available stream partitions and verify lag falls.
- Configure HPA metrics and cluster autoscaler together; CPU-only worker autoscaling is insufficient for backlog control. Add a lag-based KEDA scaler for production.
- Keep broker retention longer than the maximum recovery window and test worker replay. Archive paths are deterministic, allowing safe overwrites during replay.
- Patch Python dependencies/base images on a regular cadence; rebuild and scan images before rollout.
- Back up Redis only if its serving state has value beyond the replayable archive; otherwise document recovery by replay.
- Rotate HMAC keys and managed identity credentials using an approved, monitored process. Reconcile pseudonymized state after key changes.
- Use rolling deployments, graceful shutdown, and a non-zero termination grace period. Confirm consumer offsets before maintenance.

## Troubleshooting

| Symptom | Checks |
|---|---|
| API not ready | Inspect pod logs; verify Event Hubs endpoint, identity token permissions, Redis DNS/TLS, and namespace config |
| Kafka transport timeout | Verify DNS and outbound TCP 9093 from AKS, Event Hubs public-network/firewall settings, and the AKS subnet's egress rules. A successful token request alone does not prove broker connectivity. |
| Events accepted but no recommendations | Check worker replicas/logs, consumer lag, partitions, Redis connectivity, and event type/track values |
| Authentication error to Event Hubs | Verify workload identity label and federation subject/audience; confirm correct namespace and sender/receiver roles |
| Blob authorization failure | Confirm worker managed identity has Blob data-plane write role at the correct account/container scope |
| Consumer not scaling | Consumer parallelism cannot exceed active partitions; check partition count and group lag |
| DLQ grows | Inspect error metadata without exposing payloads; remediate input/schema or downstream issue, then replay with a controlled procedure |
| Local Compose cannot start | Confirm `.env` exists, Docker is running, ports 8000/19092 are free, and Compose health checks pass |

## Spark batch job

Install Java (required by Spark), then install `jobs/requirements-spark.txt`. Local Compose event records use a named volume; copy them into the workspace before running Spark on the host:

```powershell
New-Item -ItemType Directory -Force data/events | Out-Null
docker compose cp worker:/app/data/events/. data/events
python -m pip install -r jobs/requirements-spark.txt
spark-submit jobs/spark_batch.py --input data/events --output data/analytics
```

For a distributed run, provide Spark with an access connector/configuration for the Blob archive URI and a managed identity with read-only access. The sample job accepts Spark-readable paths; cloud connector setup is environment-specific and is not embedded in the prototype.

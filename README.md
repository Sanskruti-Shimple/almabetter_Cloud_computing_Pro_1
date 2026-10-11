# Streamify: Real-Time Music Analytics

A student-scale prototype for a Spotify-style distributed music platform. It accepts play, like, and skip events over a REST API, streams them through Kafka, updates Redis rankings in a worker, archives pseudonymized events, and includes a Spark batch analytics job.

> This is an educational prototype, not Spotify software and not a production music-delivery service. It processes interaction metadata; it does not store or stream copyrighted audio.

## Architecture at a glance

```text
Clients -> FastAPI -> Kafka / Azure Event Hubs -> Stream worker -> Redis
                                                |                |
                                                +-> Blob archive +-> Recommendations API
```

The local stack uses Redpanda (Kafka API), Redis, Docker Compose, and local JSON event archives. The Azure deployment profile uses AKS, Azure Event Hubs, Azure Blob Storage, and workload identity. See [the architecture diagram](.github/modernize/assessment/engines/facts/architecture-diagram.md).

## Run locally

Prerequisites: Docker Desktop with Compose, Python 3.11+ for tests and the Spark job.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

API: `http://localhost:8000/docs`; readiness: `http://localhost:8000/health/ready`; metrics: `http://localhost:8000/metrics`.

Replace the placeholder read/write tokens and HMAC key in `.env` with random values. Then submit an event using the write-scope token:

```powershell
$writeToken = (Get-Content .env | Where-Object { $_.StartsWith('API_WRITE_TOKEN=') }).Substring('API_WRITE_TOKEN='.Length)
$headers = @{ Authorization = "Bearer $writeToken" }
$body = @{
  event_type = "play"
  user_id = "student-user-1"
  track_id = "track-42"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/events `
  -Headers $headers -ContentType "application/json" -Body $body
```

After the worker processes the event, request recommendations using the separate read-scope token:

```powershell
$readToken = (Get-Content .env | Where-Object { $_.StartsWith('API_READ_TOKEN=') }).Substring('API_READ_TOKEN='.Length)
$headers = @{ Authorization = "Bearer $readToken" }
Invoke-RestMethod "http://localhost:8000/v1/recommendations?user_id=student-user-1" -Headers $headers
```

The API hashes user identifiers with HMAC before publishing. Never use real personal information in the demo. These shared bearer tokens are for the prototype; replace them with per-user OAuth/Entra authentication before production.

## Validate and explore

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

- Load and graph actual Locust measurements: see [performance testing](docs/performance-testing.md).
- Copy the Compose archive and run Spark batch aggregation as described in [deployment documentation](docs/deployment.md).
- Deployment, security, privacy, proposal, cost, presentation notes, and interview Q&A are in [`docs/`](docs/).
- Kubernetes examples are in [`deploy/kubernetes/`](deploy/kubernetes/).

The local compose stack is for development and testing only. It intentionally does not expose the Kafka broker outside the host or enable authentication on the isolated development network. Cloud deployments must use TLS, Event Hubs authentication, private networking where feasible, and Kubernetes secrets/workload identity as described in the deployment guide.

## Main endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health/live` | Process liveness; internal probe |
| `GET` | `/health/ready` | Checks Redis and Kafka connectivity; internal probe |
| `POST` | `/v1/events` | Write-scope bearer token required |
| `GET` | `/v1/recommendations?user_id=...` | Read-scope bearer token required |
| `GET` | `/metrics` | Prometheus metrics; keep internal |

Recommendations are popularity-based and intended to demonstrate a serving path, not production personalization. See the [proposal](docs/system-proposal.md) for limitations and future work.

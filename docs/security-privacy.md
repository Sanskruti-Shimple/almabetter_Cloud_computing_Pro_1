# Privacy and Security Report

## Controls implemented

| Area | Prototype control |
|---|---|
| Input | Pydantic schema validation, strict field allow-list, bounded identifier lengths, safe identifier character set |
| User identity | HMAC-SHA-256 pseudonymization before broker publication; raw ID is not included in the serialized event |
| Transport | Cloud Event Hubs connection uses `SASL_SSL` and OAuth bearer tokens from Azure `DefaultAzureCredential`; client-facing traffic must terminate at HTTPS ingress |
| Storage | Azure Blob access uses `DefaultAzureCredential`; enable storage encryption at rest, private endpoints, and soft delete/versioning in the Azure account |
| Access | Separate API and worker managed identities; assign only Event Hubs Data Sender / Receiver and necessary Blob data roles. API write and recommendation read endpoints require different bearer scopes |
| Runtime | Non-root containers, read-only root filesystem, dropped Linux capabilities, resource limits, health probes, restricted namespace policy |
| Resilience | Broker retention, manual offset commits after sink success, deterministic archive names, per-scope Redis atomic deduplication, bounded retry and dead-letter routing |
| Observability | Prometheus metrics avoid user identifiers; error logs limit payload exposure and do not log request bodies |

The `/metrics` endpoint is intended for an internal scraper and must not be exposed publicly by the ingress.

## Privacy and compliance

Pseudonymization reduces direct exposure but is not anonymization: a stable HMAC identifier remains linkable and may be personal data under GDPR/CCPA. The prototype uses shared bearer credentials per endpoint scope, not individual user authentication; production should validate Entra ID/OAuth JWTs and apply per-user authorization. Production use also requires a documented purpose and lawful basis, privacy notice, data-subject access/deletion workflows, retention schedule, processor agreements, and regional residency review. The prototype does not implement consent management, subject export/deletion, or legal compliance certification.

Never put names, email addresses, access tokens, payment data, or other direct identifiers in user or track IDs. HMAC keys must be random, at least 32 characters, kept in a managed secret store, rotated under a versioned migration plan, and never committed or built into an image. Key rotation changes pseudonyms, so coordinate rotation with retained rankings and retention windows.

## Threats and mitigations

| Threat | Mitigation and remaining work |
|---|---|
| Identifier injection or oversized payload | Strict schema and length/character checks; add gateway request-size and rate limits in deployment |
| Credential theft | Workload identity, short-lived OAuth token, no static cloud credentials; protect local `.env` |
| Interception | TLS to clients and SASL_SSL to Event Hubs; private networking and certificate validation in cloud |
| Unauthorized service access | Managed identity least privilege, private Redis, Kubernetes restricted namespace; add end-user OAuth/JWT before public exposure |
| Replay or duplicate delivery | Event UUID, deterministic archive path, Redis Lua idempotency, manual Kafka commit |
| Poison event / denial of service | Bounded retries and dead-letter topic; monitor DLQ and apply ingress quotas |
| Data loss or insider error | Blob versioning/soft-delete, broker retention, audit logging, restore drills; these are deployment requirements, not configured by the app |
| Dependency or image compromise | Pin production image digests, run dependency and container scans, patch base images, sign artifacts |
| Recommendation abuse | No user authentication/rate limiting in the demo; restrict network access until identity middleware and quotas are deployed |

## Security validation checklist

- [ ] Set a production-random HMAC key in a secret manager and verify it is absent from source, image layers, and logs.
- [ ] Verify the API sees only required Event Hubs sender permissions and worker only receiver plus Blob write permissions.
- [ ] Verify AKS workload identity and TLS connection to Event Hubs; block public storage/Redis access where feasible.
- [ ] Run dependency scanning and an image scan for each release.
- [ ] Test malformed fields, oversized values, repeated events, broker outage, Redis outage, and DLQ processing.
- [ ] Define retention, deletion, access request, breach response, and key-rotation procedures before real user data is accepted.

This document describes engineering controls and does not constitute legal advice or a claim of GDPR/CCPA certification.

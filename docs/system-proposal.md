# System Proposal

## Problem statement

A music-streaming service must accept large volumes of user interactions, update live popularity signals, return recommendations quickly, and retain useful event history without exposing personal identity. A single-process application or synchronous database write per interaction is likely to become a bottleneck and makes failure recovery difficult. Streamify demonstrates a modular, horizontally scalable event-processing design while intentionally limiting the prototype to interaction metadata rather than audio delivery.

## Objectives and scope

### Objectives

- Accept and validate play, like, and skip events through a REST API.
- Pseudonymize user identifiers before they enter the event stream.
- Buffer events durably in a partitioned Kafka-compatible broker.
- Process events independently, deduplicate retries, update live recommendation signals, and archive events.
- Provide health checks, operational metrics, container images, orchestration examples, and reproducible test procedures.
- Demonstrate both streaming processing and Spark batch aggregation.

### In scope

FastAPI ingestion and recommendation endpoints; Kafka/Redpanda locally and Azure Event Hubs in cloud; Redis sorted-set counters; local or Azure Blob JSON archival; a Spark batch rollup; Docker Compose and AKS manifests; security, privacy, performance, deployment, and cost documentation.

### Out of scope

Audio encoding, licensing, DRM, billing, production identity federation for end users, machine-learning model training, multi-region active-active writes, and any claim of Spotify internal architecture. The recommendation rule is popularity-based and demonstrative.

## Requirements

### Functional

1. Ingest validated interaction events and return an event identifier.
2. Route accepted events to a durable broker instead of synchronously computing recommendations.
3. Aggregate event scores in Redis and archive a pseudonymized event record.
4. Return popular tracks while excluding tracks already seen by the requesting pseudonymous user.
5. Recover from duplicate delivery through idempotent processing and route poison messages to a dead-letter topic.
6. Run a Spark aggregation over archived JSON events.

### Non-functional targets for a testable prototype

| Attribute | Design target | Measurement |
|---|---|---|
| Availability | Redundant API and worker replicas; broker retains queued events | Uptime and restart/recovery observation |
| Ingestion latency | p95 below 250 ms at 100 concurrent clients in the stated test environment | Locust response-time histogram |
| Processing delay | p95 under 5 seconds while consumer capacity exceeds input rate | Event timestamp to Redis visibility |
| Scalability | Add API replicas independently from partitioned stream consumers | Replicas, consumer lag, throughput |
| Security | TLS for cloud data paths; least-privilege identities; no raw user identifier in broker or archive | Configuration review and test fixtures |
| Durability | Broker retention plus idempotent archival to object storage | Restart worker and verify replay |

These are evaluation targets, not measured results or guarantees. Record actual environment and results in the performance report.

## Design principles

- Decouple request acceptance from event processing with a broker.
- Prefer at-least-once delivery with idempotent sinks rather than claiming end-to-end exactly-once behavior across Redis and Blob Storage.
- Scale stateless API pods and partition-bound workers independently.
- Keep personally identifying values out of logs, topic payloads, and storage.
- Use managed cloud services and workload identity in cloud deployment; keep credentials out of images and source files.
- Make service readiness explicit and fail visibly when dependencies are unavailable.

## High-level architecture

```text
Mobile or web client
        |
        v
HTTPS ingress and load balancer
        |
        v
FastAPI ingestion and recommendation API
        |
        v
Partitioned Kafka stream / Azure Event Hubs
        |
        v
Consumer group: event processors
      /                         \
     v                           v
Redis live ranking         Blob event archive
     |                           |
     +--> Recommendations API    +--> Apache Spark batch rollup
```

### Data flow

The client submits a user interaction over HTTPS. API validation rejects malformed identifiers and extra fields; HMAC-SHA-256 converts the supplied user identifier to a stable pseudonym before publishing. The API returns `202 Accepted` after queueing. Partitioned consumers archive the event and atomically update Redis using a Lua deduplication script. Offsets are committed after both sinks succeed; failures are retried, then sent to a dead-letter topic. A separate query path reads cached rankings. Spark can aggregate archived events offline without touching the live API.

## Technology choices

| Technology | Role | Reason |
|---|---|---|
| Python 3.12 and FastAPI | REST API and worker | Typed request validation, concise services, async-friendly ecosystem |
| Confluent Kafka client | Kafka-compatible producer/consumer | Partitioned stream, consumer groups, delivery callbacks, OAuth bearer support |
| Redpanda | Local broker | Kafka API compatibility without a multi-container development cluster |
| Azure Event Hubs | Managed cloud event stream | Managed partitions, retention, and Kafka endpoint |
| Redis | Live per-user/global sorted-set rankings | Low-latency reads and atomic Lua update/deduplication |
| Azure Blob Storage | Cloud event archive | Durable, low-cost object storage with managed identity support |
| Apache Spark | Offline batch aggregation | Distributed, parallel processing of archived event files |
| Docker and Kubernetes/AKS | Packaging and orchestration | Reproducible deployment, health probes, rolling updates, horizontal scaling |
| Prometheus metrics and Locust | Observability and load testing | Standard service metrics and repeatable traffic generation |

## Reliability and trade-offs

The prototype favors availability for event intake: `202` means the broker accepted the event, while ranking updates are eventually consistent. The broker decouples spikes from consumers. Six local topic partitions and three consumer replicas are demonstration settings; throughput depends on partition count, partition key, broker capacity, and consumer work. A user-keyed partition would preserve user ordering but can create hot partitions; event-id keys distribute load more evenly but do not preserve per-user ordering. Current publishing keys by event ID.

Redis ranking state is a serving cache, not the canonical record. Blob events provide replay input. The processor intentionally uses at-least-once delivery: archive object names are deterministic, and Redis Lua scripts prevent a retried event from incrementing counters twice. User and global rankings use separate hash slots so the scripts work with Redis Cluster; retries repair partial progress between the two scripts. Broker retention is seven days and deduplication markers live eight days. Ranking sets are bounded to control memory. Cross-system atomic transactions are not claimed.

## Industry-pattern comparison

This comparison uses publicly documented distributed-systems practices and common industry patterns. It does not claim knowledge of Spotify's internal architecture.

| Concern | Streamify prototype | Common large-platform practice / standard |
|---|---|---|
| Event ingestion | Kafka-compatible partitioned broker decouples API from workers | Event logs and queues buffer bursts and isolate services |
| Processing guarantees | At-least-once consumption with idempotent sinks and replay | Explicit delivery semantics, deduplication, schema governance, and replay |
| Serving path | Redis sorted sets provide a small low-latency recommendation demo | Dedicated online stores/caches with measured freshness and SLOs |
| Analytics | Spark batch rollup over archived JSON | Distributed stream and batch computation over governed data lakes |
| Identity and encryption | Scoped shared bearer tokens in the prototype; cloud service identities; TLS requirements | Per-user OAuth/OIDC identity, fine-grained authorization, key management, and encrypted links |
| Resilience | Pod replicas, health probes, bounded retries, and a dead-letter stream | Multi-zone deployment, tested recovery objectives, backpressure, and on-call alerting |
| Privacy | HMAC pseudonyms, bounded rankings, and documented retention | Data minimization, purpose limitation, subject-rights workflows, and audited retention |

Streamify is intentionally much smaller than a production streaming platform: it is single-region, has no audio/CDN path, uses a popularity heuristic rather than a trained model, and does not claim millions-user capacity. The performance report therefore defines repeatable measurements instead of asserting unverified scale.

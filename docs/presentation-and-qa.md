# Presentation Notes and Interview Q&A

## 12-15 minute video outline

## Live demo

- Demo URL: [http://48.194.77.114](http://48.194.77.114)
- API docs: [http://48.194.77.114/docs](http://48.194.77.114/docs)
- Health checks verified HTTP 200 for `/health/live`, `/health/ready`, and `/docs` on 2026-10-11.
- This is a temporary HTTP endpoint; bearer tokens are not encrypted in transit. Use demo-only credentials and no personal data. The API currently has 2 of 3 replicas ready; do not claim production availability or verified end-to-end event processing.

1. **Introduction (1.5 min):** Explain Streamify as an educational real-time interaction analytics platform, not an audio streaming implementation. State the design target: large bursts of play/like/skip events with independent serving and processing.
2. **Problem and requirements (2 min):** Describe durable ingestion, low-latency recommendations, high availability, privacy, fault tolerance, and why a single synchronous service is a bottleneck.
3. **Architecture (2.5 min):** Walk the request from HTTPS client through FastAPI, Kafka/Event Hubs, consumer group, Redis, Blob archive, recommendation endpoint, and Spark batch rollup.
4. **Real-time processing (2 min):** Explain partitions, consumer groups, broker buffering, at-least-once delivery, Redis Lua deduplication, deterministic Blob object keys, retries, and dead-letter routing. Distinguish stream processing from Spark batch aggregation.
5. **Scaling (2 min):** Scale API replicas independently. Scale workers up to partition count; mention consumer lag as the production scaling signal. Explain HPA and the included Kubernetes settings.
6. **Security and privacy (1.5 min):** Discuss HMAC pseudonymization, TLS/SASL_SSL, workload identity, least privilege, encrypted cloud storage, and the fact that pseudonymized data is not automatically anonymous or compliant.
7. **Deployment and cost (1.5 min):** Demonstrate Docker Compose, then describe AKS/Event Hubs/Blob deployment. Show a dated calculator export and a real Locust chart after you have run the tests.
8. **Trade-offs and next steps (2 min):** Discuss eventual consistency, cost/performance, partition limits, Redis cardinality, and production improvements such as authenticated end users, lag-based autoscaling, multi-region recovery, and an ML recommender.

## Follow-up questions

### 1. How would you design this system for millions of concurrent users?

Use globally distributed edge ingress, stateless API replicas, regional partitioned event streams, per-region processing, and a distributed cache. Capacity-plan from peak events per second and event size, not only registered users. Partition by a key that balances ordering needs against hot keys; autoscale workers from consumer lag and maintain enough partitions. Add multi-region disaster recovery, rate limiting, load tests, and explicit SLOs. This prototype demonstrates the separation of those layers but does not itself prove million-user capacity.

### 2. What trade-offs did you make between consistency and availability?

Event intake is asynchronous: the API acknowledges broker acceptance before Redis rankings update, so recommendations are eventually consistent. This keeps the intake path available during processing slowdowns. The archive is treated as the durable history; Redis is rebuildable serving state. Strong global consistency would increase latency and coordination cost and is not needed for popularity signals.

### 3. How do you ensure fault tolerance?

The broker buffers events, consumer offsets commit only after archive and Redis operations complete, retries are bounded, duplicate Redis updates are atomic/idempotent, and exhausted messages enter a dead-letter topic. Kubernetes replicas and probes provide process-level recovery. Production requires multi-zone managed services, tested backups, broker retention, alerting, and disaster-recovery exercises.

### 4. How would you reduce latency?

Measure API p95/p99, broker publish time, consumer lag, Redis time, and network hops separately. Keep request handling small, use regional ingress and caches, avoid synchronous downstream work, right-size partitions and consumers, use connection reuse, and profile serialization. Do not reduce durability or security controls without explicitly changing the requirements.

### 5. How do you handle data synchronization across multiple services?

Publish an immutable versioned event contract with schema validation and compatibility rules. Consumers use idempotency keys and record offsets only after successful side effects. Use deterministic archive paths and replay for recovery. For complex state changes, introduce an outbox/CDC mechanism, schema registry, and reconciliation jobs; this prototype does not claim a distributed transaction.

## Q&A limitations to state clearly

- The prototype uses popularity ranking, not a trained recommendation model.
- It demonstrates metadata processing only and contains no licensed audio.
- The local broker has one replica and is for development; cloud durability depends on configured Azure service tiers and zone redundancy.
- GDPR/CCPA compliance requires organizational and operational controls beyond pseudonymization.
- Performance thresholds are targets; present only your own reproducible measurements.

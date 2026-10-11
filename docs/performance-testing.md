# Performance Testing Report

## Status and honesty of results

This repository includes a repeatable load-test plan and plotting tool, but no cloud or benchmark environment was available when the project was assembled. Therefore, it reports **no fabricated latency, throughput, uptime, or recovery measurements**. Run the scenarios below and append the generated CSV, chart, environment details, and observations to produce measured results.

## Test setup

Use a dedicated test environment, not production. Record CPU/memory limits, broker partitions, Redis SKU, client machine, region, network path, software versions, and date. Start local services with `docker compose up --build`; verify `/health/ready` returns `ready`. Use `locustfile.py` for mixed event submissions and recommendation reads.

## Scenarios

| Scenario | Procedure | Metrics and pass criteria |
|---|---|---|
| Baseline | 20 users for 5 minutes; warm-up 1 minute | Record RPS, p50/p95/p99, error rate, and consumer delay |
| Peak load | Ramp 50, 100, 250, then 500 users for 3 minutes each | Target p95 ingestion below 250 ms and error rate below 1% at the agreed test load |
| Stress | Increase users until the error rate exceeds 5% or p95 exceeds 1 second; hold 5 minutes | Identify saturation point, queue growth, and recovery after load drops |
| Worker fault | Stop worker for 60 seconds while publishing; restart it | Events remain queued, consumer catches up, and no duplicate score increments occur |
| API scale | Compare 1, 3, and 6 API replicas under same traffic | Compare throughput, p95, CPU and memory |
| Worker scale | Compare 1, 3, and 6 workers with topic partition count recorded | Verify scaling is bounded by available partitions and observe consumer lag |
| Vertical scale | Double worker CPU/memory limits at fixed replicas | Compare processing delay and cost per processed event |

For the local Compose demonstration, Locust runs from the host:

```powershell
python -m locust -f locustfile.py --host http://localhost:8000 `
  --headless -u 100 -r 10 -t 5m --csv locust_baseline
```

Plot the measured time series:

```powershell
python scripts/plot_metrics.py locust_baseline_stats_history.csv `
  --output performance-baseline.png
```

The graph contains requests/second, failures/second, p95 latency, and concurrent users. Preserve the Locust CSV files with the submitted report. The worker's logs show processed event IDs but do not currently expose consumer lag as a Prometheus metric; production evaluation should add broker lag monitoring before scaling consumers automatically.

## Results template

| Run | Environment | Users | Duration | Throughput (req/s) | p95 (ms) | Error rate | Recovery time |
|---|---|---:|---|---:|---:|---:|---:|
| Baseline | Fill after execution | | | | | | |
| Peak | Fill after execution | | | | | | |
| Worker fault | Fill after execution | | | | | | |

Attach `performance-baseline.png` and discuss bottlenecks observed. Distinguish API acceptance latency from end-to-end processing delay; they are not interchangeable.

## Expected constraints and interpretation

API scaling is stateless and usually responds to CPU, request rate, and broker capacity. Worker throughput is partition-bound: adding replicas beyond the partition count does not increase active consumer parallelism. Redis sorted sets are bounded to the top 1,000 tracks per pseudonymous user and top 100,000 globally, with expiring keys. Blob request volume, cross-zone traffic, and logging can become material costs.

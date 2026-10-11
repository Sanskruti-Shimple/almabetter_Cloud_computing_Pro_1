# Cost Analysis

## Planning scenario

This is an order-of-magnitude planning worksheet, not an Azure quote. Pricing depends on region, agreement, SKU, redundancy, network topology, logging ingestion, and current rates. Use the Azure Pricing Calculator and current regional pricing before procurement. The current constrained teaching/demo scenario is East US, two fixed AKS system nodes (limited by four available regional vCPUs), one Standard Event Hubs throughput unit, a small LRS Blob archive, Key Vault, Basic ACR, in-cluster Redis, and modest test traffic. The template does not provision managed Redis, private endpoints, an ingress, or a monitoring workspace. This is not a production estimate for millions of concurrent listeners.

## Cost model

| Cost component | Sizing assumption | Monthly cost model |
|---|---|---|
| AKS worker compute | 2 x Standard_D2as_v7 Linux nodes, 730 hours; AKS Free management tier | `2 x hourly VM rate x 730` |
| OS disks and load balancing | 2 x 64 GiB managed disks; AKS standard load balancer for outbound traffic | Disk GB-month + load balancer hours/rules + outbound traffic |
| Event Hubs | Standard tier, 1 throughput unit, 730 hours, plus ingress/egress beyond included allowance | `1 x TU-hour rate x 730 + metered throughput` |
| Blob Storage | Hot LRS, 30-day retention; estimate capacity and operations from measured events | Capacity GB-month + operation charges + redundancy |
| Redis | Single in-cluster demonstration replica; compute/memory included in AKS node capacity | No separate managed-cache line item; included pod resources consume node capacity |
| Key Vault | Standard tier; estimate secret operations and any network charges | Secret operations + applicable networking |
| Container Registry | Basic registry for two images and build artifacts | Registry tier monthly rate + stored GB |
| Monitoring | Not provisioned by the current Bicep template; add separately for production | Ingested GB x regional rate + retention over included amount |
| Network egress | Usage-dependent; remote ACR build and Blob/Event Hubs traffic may incur transfer charges | Regional egress rate x billable GB |

No fixed total is presented because current East US retail rates, billing agreement, and workload volumes have not been verified. Populate each line with current calculator or invoice data before presenting a total; the two always-on AKS nodes are likely the dominant baseline cost.

The quantities below are explicit example inputs. Populate them and replace the planning band with a dated calculator export before procurement:

| Input | Example value | Replace with verified value |
|---|---:|---|
| Region | East US | |
| AKS nodes | 2 x D2as_v7 | |
| Node uptime | 730 hours/month | |
| Event Hubs throughput | 1 TU | |
| Raw event volume | 1 million events/day | |
| Average event payload | 1 KiB | |
| Archive retention | 30 days | |
| Blob storage | 100 GiB Hot LRS | |
| Data egress | 100 GiB/month | |
| Log ingestion | Not included in current deployment | |

### Workload arithmetic

At 1,000,000 events/day and an average 1 KiB encoded event, raw ingress is about `1,000,000 x 1 KiB x 30 = 30,000,000 KiB`, or about 28.6 GiB/month before broker metadata, object overhead, replication, logs, and derived data. At 10 million events/day the corresponding raw payload is about 286 GiB/month. Size Event Hubs partitions, Redis memory, Blob capacity, and worker replicas using measured event size and peak rate rather than monthly averages.

For a final estimate, fetch current rates for the selected region/SKUs, enter actual workload assumptions in the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/), include tax/support/networking where applicable, and attach a dated calculator export. Pricing changes frequently; this repository deliberately does not invent a fixed dollar total without validated rates.

## Cost controls

- Use autoscaling with minimum replicas sized for availability and maximums tied to an explicit budget/alert.
- Scale workers based on consumer lag and partitions; avoid idle replicas beyond useful parallelism.
- Set Event Hubs retention to the recovery and replay requirement, not an arbitrary indefinite window.
- Use Blob lifecycle policies to move old archives to Cool/Cold tiers or delete data according to retention policy.
- Reduce log verbosity and retention; exclude sensitive event payloads from logs.
- Right-size Redis based on observed cardinality, TTL, and memory headroom; evict expired data and cap ranking sets.
- Use reservations/savings plans for stable compute only after workload and commitment terms are validated. Keep burst capacity on pay-as-you-go.
- Apply budgets and alerts; review cross-zone and internet egress before enabling broad replication.
- Stop non-production clusters outside class/test windows and remove unused public IPs, disks, and old images.

## Cost versus performance

More Event Hubs throughput, partitions, Redis capacity, worker CPU, and replicas can reduce backlog and latency, but add recurring cost. The class experiment should graph p95 latency and consumer lag alongside estimated per-hour run cost and stop scaling after the target SLO is met.

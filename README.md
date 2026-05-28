# SDLS v3 — Production-Grade Distributed Observability Platform

> **Incremental modernization** of the original distributed logging system.  
> Every architectural decision is explained. No rewrites — only deliberate upgrades.

---

## What Changed in v3

| Concern | v2 | v3 |
|---|---|---|
| Service discovery | Hardcoded IPs in `constants.py` | Redis node registry (`sdls:registry:<name>`) |
| EC2 networking | Static IPs + `set_static_ip.sh` | Zero hardcoded IPs — Docker DNS + host networking |
| Session management | In-memory per-node | Redis-backed (DB 1), 30-min sliding TTL |
| Service startup | Plain Flask `app.run` | Role-aware `registry.py` → register + heartbeat |
| Dashboard UI | Bootstrap 4 | Custom design system (dark + light theme, CSS vars) |
| Topology map | Static node list | Canvas-drawn live graph from Redis registry |
| Compose strategy | Single monolithic file | Per-role files: `system{1,2,3}-compose.yml` |
| Deployment | Manual IP setup | `scripts/deploy.sh` — auto-detects IP, picks compose |
| Config management | Scattered constants | `config/sdls-config.json` → Redis `sdls:config` |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  EC2 System 1                 │  EC2 System 2                        │
│  ├── api-gateway  :5000       │  ├── payment-service     :5002       │
│  └── order-service :5001      │  ├── backup-payment      :5009       │
│                               │  └── inventory-service   :5003       │
├───────────────────────────────┴──────────────────────────────────────┤
│  EC2 System 3                                                        │
│  ├── notification-service :5004   ├── logging-service :5005          │
│  ├── backup-logging       :5010   ├── coordinator     :5007          │
│  ├── time-sync-service    :5008   ├── dashboard       :5006          │
│  ├── redis                :6379   └── mongodb         :27017         │
└──────────────────────────────────────────────────────────────────────┘
              ↑ All inter-service routing via Redis node registry ↑
```

### Key Principles

1. **Redis is the only shared hard dependency.**  
   All services know Redis's address (`REDIS_HOST` env var).  
   Everything else — service URLs, node IPs — is discovered from Redis.

2. **Zero hardcoded IPs in source code.**  
   `constants.get_service_url(name)` resolves at call-time:  
   env var → Redis registry → Docker DNS fallback.

3. **Docker-native networking.**  
   Single-host: Docker bridge, container DNS names.  
   Multi-host EC2: `network_mode: host`, Redis registry provides IPs.

4. **Role-aware startup.**  
   `registry.register_self()` + `start_heartbeat()` called in every service.  
   Registry TTL = 90 s. Heartbeat refreshes every 30 s.

---

## Quick Start (Single Host / Dev)

```bash
# Clone and configure
cp .env.example .env
# Edit .env — change SECRET_KEY and DASHBOARD_PASSWORD

# Build and launch everything
docker compose up -d --build

# Watch it come up
docker compose logs -f coordinator dashboard

# Open the dashboard
open http://localhost:5006
```

---

## EC2 Multi-Host Deployment

### Prerequisites
- 3 EC2 instances (t3.small or larger), same VPC, same security group
- Security group allows inbound TCP on ports **5000–5010, 6379, 27017** between instances
- Git or scp to copy the project to each instance

### Step 1 — Bootstrap all instances
```bash
# On each EC2 instance (run as root or with sudo)
bash scripts/ec2-setup.sh
```

### Step 2 — Deploy System 3 first (infrastructure node)
```bash
# On EC2 System 3 instance
cd /opt/sdls
SYSTEM_ROLE=system3 ./scripts/deploy.sh
# Note the System 3 private IP (output at start of script, or: hostname -I)
```

### Step 3 — Deploy System 2
```bash
# On EC2 System 2 instance
cd /opt/sdls
REDIS_HOST=<system3_private_ip> SYSTEM_ROLE=system2 ./scripts/deploy.sh
```

### Step 4 — Deploy System 1
```bash
# On EC2 System 1 instance
cd /opt/sdls
REDIS_HOST=<system3_private_ip> SYSTEM_ROLE=system1 ./scripts/deploy.sh
```

### Step 5 — Verify
```bash
# On any instance with redis-cli or curl
REDIS_HOST=<system3_private_ip> ./scripts/status.sh

# Dashboard at:
open http://<system3_public_ip>:5006
```

---

## Service Registry Deep Dive

Every service calls `registry.register_self(service_name)` at startup.

**Redis key:** `sdls:registry:<service-name>`  
**Value (JSON):**
```json
{
  "host":       "10.0.1.42",
  "port":       5002,
  "service":    "payment-service",
  "role":       "system2",
  "started_at": "2024-01-15T10:30:00Z",
  "pid":        1234,
  "version":    "v3"
}
```
**TTL:** 90 seconds (refreshed every 30 s by heartbeat thread)

**URL resolution order** (`constants.get_service_url`):
1. Env var: `PAYMENT_SERVICE_URL`
2. Redis registry host + known port
3. Docker DNS fallback (container name)

---

## Dashboard Features

| Page | Description |
|---|---|
| `/` (Overview) | Cluster health, EC2 nodes from registry, live log feed |
| `/topology` | Canvas-rendered service graph, latency table, circuit breakers |
| `/logs` | Filterable log table + live Socket.IO stream |
| `/analytics` | Request volume chart, status distribution, per-service breakdown |
| `/errors` | Error/warning stream, failover timeline |

**Themes:** Click `☀/☾` in the sidebar. Preference persisted in `localStorage`.

---

## Security Notes for Production

1. Change `SECRET_KEY`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` in `.env`
2. Put the dashboard behind an ALB + HTTPS; restrict port 5006 in the security group
3. Restrict Redis (port 6379) to VPC CIDR only — never expose to 0.0.0.0/0
4. Restrict MongoDB (port 27017) to VPC CIDR only
5. Use AWS Secrets Manager or SSM Parameter Store instead of `.env` files in prod

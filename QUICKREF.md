# SDLS v3 — Quick Reference

## Deploy Order (ALWAYS System 3 first)
```
System 3 (infra) → System 2 (payment/inventory) → System 1 (gateway/orders)
```

## The ONE Variable That Connects Everything
```bash
REDIS_HOST=<System3_private_IP>   # Set this on Systems 1 & 2
```

## Deploy Commands

| Node | Command |
|------|---------|
| System 3 | `SYSTEM_ROLE=system3 ./scripts/deploy.sh` |
| System 2 | `REDIS_HOST=10.0.1.X SYSTEM_ROLE=system2 ./scripts/deploy.sh` |
| System 1 | `REDIS_HOST=10.0.1.X SYSTEM_ROLE=system1 ./scripts/deploy.sh` |
| Single host (dev) | `docker compose up -d --build` |

## Key URLs (replace IPs)

| URL | Purpose |
|-----|---------|
| `http://<SYS3_PUBLIC>:5006` | Dashboard (login required) |
| `http://<SYS1_PUBLIC>:5000/api/order` | Place test order (POST) |
| `http://<SYS3_PRIVATE>:5007/api/cluster/state` | Cluster state JSON |
| `http://<SYS3_PRIVATE>:5007/api/cluster/registry` | Live service registry |

## Common Commands

```bash
# See all registered services
./scripts/status.sh

# Full diagnostics
./scripts/troubleshoot.sh

# Watch logs live
docker compose -f system3-compose.yml logs -f --tail=30

# Restart one service
docker compose -f system3-compose.yml up -d --no-deps coordinator

# Redis CLI
docker exec -it sdls-redis redis-cli

# Check registry in Redis
docker exec sdls-redis redis-cli KEYS "sdls:registry:*"

# MongoDB shell
docker exec -it sdls-mongodb mongosh distributed_logging

# Count logs
docker exec sdls-mongodb mongosh distributed_logging \
  --eval "db.logs.countDocuments()"
```

## Port Map

```
:5000  api-gateway       (EC2 #1, VPC-internal)
:5001  order-service     (EC2 #1, VPC-internal)
:5002  payment-service   (EC2 #2, VPC-internal)
:5003  inventory-service (EC2 #2, VPC-internal)
:5004  notification      (EC2 #3, VPC-internal)
:5005  logging-service   (EC2 #3, VPC-internal)
:5006  dashboard         (EC2 #3, PUBLIC)
:5007  coordinator       (EC2 #3, VPC-internal)
:5008  time-sync         (EC2 #3, VPC-internal)
:5009  backup-payment    (EC2 #2, VPC-internal)
:5010  backup-logging    (EC2 #3, VPC-internal)
:6379  Redis             (EC2 #3, VPC-ONLY)
:27017 MongoDB           (EC2 #3, VPC-ONLY)
```

## Troubleshooting Matrix

| Symptom | Check | Fix |
|---------|-------|-----|
| Dashboard unreachable | SG port 5006 open? | Add inbound 5006 TCP 0.0.0.0/0 |
| Services not showing in registry | Redis running? | `docker exec sdls-redis redis-cli ping` |
| Systems 1/2 can't find services | REDIS_HOST correct? | Check .env, must be System 3 private IP |
| Logs not appearing in dashboard | Socket.IO connected? | Check browser console; logging-service port 5005 reachable |
| Failover not triggering | Fail count < 3? | Coordinator polls every 10s, triggers after 3 consecutive fails |
| Build fails | Disk full? | `docker system prune -af` frees space |
| Container keeps restarting | OOM? | Increase instance type or reduce services per node |

## Security Checklist (before real traffic)
- [ ] Change DASHBOARD_PASSWORD from default
- [ ] Rotate SECRET_KEY: `openssl rand -hex 32`
- [ ] Restrict port 5006 to your IP (not 0.0.0.0/0)
- [ ] Enable NGINX + TLS (see Step 16 in the deploy guide)
- [ ] Redis on VPC-only (never expose :6379 publicly)
- [ ] MongoDB on VPC-only (never expose :27017 publicly)
- [ ] Use SSM Parameter Store for secrets (not .env files)

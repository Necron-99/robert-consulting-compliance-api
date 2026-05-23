# robert-consulting-compliance-api

A production compliance framework mapping API connecting security controls across 16 frameworks — with bi-directional links to MITRE ATT&CK threat intelligence, making compliance coverage threat-informed rather than checkbox-driven.

Live at **[compliance.robertconsulting.net](https://compliance.robertconsulting.net)**

---

## What it does

Most compliance tools answer "do we have a control for X?" This API answers "does our control coverage actually address the techniques being used against organizations like ours?" — by cross-referencing compliance frameworks with real-world adversary TTPs via MITRE ATT&CK.

**Data coverage:**
- 16 frameworks: NIST 800-53, FedRAMP, ISO 27001, GDPR, NIS2, DORA, HIPAA, PCI-DSS, SOC 2, CMMC, and more
- 6,361 controls with descriptions
- 2,200+ cross-framework control mappings (equivalent, subset, superset, related)
- 3,797 ATT&CK-to-NIST 800-53 mappings (CTID Mappings Explorer, ATT&CK v16.1)
- 467 unique ATT&CK techniques with compliance coverage

---

## API

Built with **FastAPI** on **Python 3.12**. Read-only SQLite backend fetched from S3 on pod start. Full OpenAPI docs at [api.compliance.robertconsulting.net/docs](https://api.compliance.robertconsulting.net/docs).

### Key endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /stats` | Summary counts for all frameworks and mappings |
| `GET /frameworks` | All 16 frameworks |
| `GET /frameworks/{code}/controls` | Paginated controls for a framework |
| `GET /controls/{id}/mappings` | Cross-framework mappings for a control |
| `GET /mappings` | All mappings — filterable by framework, relationship type |
| `GET /attack/techniques/{id}` | NIST 800-53 controls that mitigate an ATT&CK technique |
| `GET /attack/by-control/{control_id}` | ATT&CK techniques addressed by a NIST control |
| `GET /attack/stats` | ATT&CK mapping coverage statistics |
| `GET /search` | Full-text search across all controls |

### Example

```bash
# Which NIST 800-53 controls mitigate T1078 (Valid Accounts)?
curl https://api.compliance.robertconsulting.net/attack/techniques/T1078 | \
  jq '.nist_control_count'
# 29

# Which ATT&CK techniques does AC-2 (Account Management) address?
curl https://api.compliance.robertconsulting.net/attack/by-control/AC-2 | \
  jq '.technique_count'
# 220
```

---

## Architecture

```
CloudFront / Route 53
       │
   ingress-nginx (k3s, Hetzner)
       │
   compliance-api pod
   ├── init container: fetch compliance.db from S3
   └── FastAPI (uvicorn, single worker)
           │
       SQLite (read-only, immutable mount)
```

- **Kubernetes** — k3s on Hetzner CX33
- **Container** — multi-stage Python 3.12 slim, non-root user
- **Database** — SQLite, S3-backed, fetched by init container on pod start
- **Observability** — Prometheus metrics via `prometheus-fastapi-instrumentator`, Grafana dashboards
- **CI/CD** — GitHub Actions → GHCR image push → `kubectl rollout restart`

---

## Repository Structure

```
robert-consulting-compliance-api/
├── compliance-api/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Multi-stage container build
├── k8s/
│   ├── 00-namespace.yaml
│   ├── 01-cluster-issuer.yaml
│   ├── 02-deployment.yaml   # Deployment with S3 init container
│   ├── 03-service.yaml
│   └── 04-ingress.yaml
├── .github/
│   └── workflows/
│       └── compliance-api.yml
├── platform-ops/            # Submodule — platform operations and monitoring
└── README.md
```

---

## Data Sources

| Source | License | Coverage |
|--------|---------|----------|
| [NIST 800-53 Rev 5](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final) | Public Domain | Access control, audit, configuration, and more |
| [CTID Mappings Explorer](https://center-for-threat-informed-defense.github.io/mappings-explorer/) | Apache 2.0 | ATT&CK-to-NIST 800-53 mappings |
| Various framework sources | See `/frameworks` endpoint | ISO 27001, GDPR, HIPAA, CMMC, PCI-DSS, SOC 2, NIS2, DORA, FedRAMP |

---

## Deployment

### Prerequisites

- k3s cluster running
- cert-manager and ingress-nginx installed
- DNS: `api.compliance.robertconsulting.net` pointing to cluster IP
- AWS IAM credentials in Kubernetes Secret
- Infrastructure resources provisioned via the infrastructure repository

### First-time setup

```bash
# 1. Upload database to S3
aws s3 cp ~/compliance.db s3://<COMPLIANCE_BUCKET>/data/compliance.db

# 2. Create namespace and credentials secret
kubectl create namespace compliance-api
kubectl create secret generic aws-compliance-api-credentials \
  --namespace compliance-api \
  --from-literal=AWS_ACCESS_KEY_ID=<key> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<secret> \
  --from-literal=AWS_DEFAULT_REGION=us-east-1 \
  --from-literal=S3_BUCKET=<bucket> \
  --from-literal=S3_KEY=data/compliance.db

# 3. Apply manifests
kubectl apply -f k8s/

# 4. Verify
kubectl rollout status deployment/compliance-api -n compliance-api
curl https://api.compliance.robertconsulting.net/health
```

### Ongoing deployments

Use the deploy script from the platform-ops submodule:

```bash
./platform-ops/scripts/deploy.sh --compliance
```

---

## Local Development

```bash
cd compliance-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

DATABASE_PATH=~/compliance.db uvicorn main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the interactive documentation.

---

## Related

- **[robert-consulting-threat-api](https://github.com/Necron-99/robert-consulting-threat-api)** — Threat intelligence API (MITRE ATT&CK, CISA KEV, group attribution)
- **[robert-consulting-platform-ops](https://github.com/Necron-99/robert-consulting-platform-ops)** — Kubernetes platform operations and monitoring stack
- **[robert-consulting-content](https://github.com/Necron-99/robert-consulting-content)** — Frontend UIs for both tools

---

## Disclaimer

Compliance mappings: CTID Mappings Explorer — Apache 2.0
Reference only — not legal or operational advice.

© 2026 Robert Consulting LLC. All rights reserved.

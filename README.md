# Robert Consulting — Compliance Framework API

REST API serving the [compliance.robertconsulting.net](https://compliance.robertconsulting.net)
cross-framework mapping tool. Built with FastAPI, deployed on k3s (Hetzner Cloud).

**Live endpoint:** `https://api.compliance.robertconsulting.net`  
**API docs:** `https://api.compliance.robertconsulting.net/docs`  
**Frontend:** `https://compliance.robertconsulting.net`

---

## Overview

The compliance framework mapping database covers 16 frameworks including NIST 800-53,
FedRAMP, ISO 27001, GDPR, NIS2, DORA, HIPAA, PCI-DSS, SOC2, CMMC, and more — with
2,200+ cross-framework control mappings.

The API exposes this database as a read-only REST API for the static frontend hosted
on AWS CloudFront.

### Architecture

```
Browser
  ├── Static assets  → CloudFront (AWS S3)
  └── API calls      → api.compliance.robertconsulting.net
                            ↓
                       ingress-nginx (Hetzner k3s)
                            ↓
                       FastAPI pod
                            ↓ (on startup)
                       Init container fetches compliance.db from S3
```

### Database refresh pattern

The SQLite database is managed separately by the compliance importer and uploaded
to S3. The API pod fetches it fresh on every start.

To update the live API with new framework data:
```bash
# 1. Run the importer locally
python3 import_framework.py --db ~/compliance.db --source <new_source>

# 2. Upload to S3
aws s3 cp ~/compliance.db s3://<COMPLIANCE_BUCKET>/data/compliance.db

# 3. Restart the pod to fetch the new database
kubectl rollout restart deployment/compliance-api -n compliance-api

# 4. Verify
kubectl rollout status deployment/compliance-api -n compliance-api
```

---

## Repository Structure

```
robert-consulting-compliance-api/
├── compliance-api/
│   ├── main.py              # FastAPI application
│   ├── requirements.txt     # Python dependencies
│   └── Dockerfile           # Container build
├── k8s/
│   ├── 00-namespace.yaml    # compliance-api namespace
│   ├── 01-cluster-issuer.yaml  # cert-manager Let's Encrypt issuer
│   ├── 02-deployment.yaml   # Deployment with S3 init container
│   ├── 03-service.yaml      # ClusterIP service
│   └── 04-ingress.yaml      # ingress-nginx + TLS
├── .github/
│   └── workflows/
│       └── compliance-api.yml  # Build and push container image
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness/readiness probe |
| GET | `/stats` | Summary counts for landing page |
| GET | `/frameworks` | List all frameworks |
| GET | `/frameworks/{code}` | Single framework detail |
| GET | `/frameworks/{code}/controls` | Paginated controls for a framework |
| GET | `/domains` | List control domains |
| GET | `/canonical` | List canonical controls |
| GET | `/controls/{id}/mappings` | Cross-framework mappings for a control |
| GET | `/mappings` | All mappings with filtering and pagination |
| GET | `/search?q=...` | Full-text search across all controls |
| GET | `/docs` | Interactive OpenAPI documentation |
| GET | `/redoc` | ReDoc API documentation |

### Query parameters

**`/frameworks/{code}/controls`**
- `page` — page number (default: 1)
- `page_size` — results per page (default: 100, max: 500)
- `include_description` — include full control text (default: false)

**`/mappings`**
- `source_framework` — filter by source framework code (e.g., `NIST-800-53`)
- `target_framework` — filter by target framework code (e.g., `ISO-27001`)
- `relationship` — filter by type: `equivalent`, `subset`, `superset`, `related`
- `page`, `page_size` — pagination

**`/search`**
- `q` — search term (min 2 chars, searches control_id, name, description)
- `framework` — optional framework filter
- `page`, `page_size` — pagination

---

## Container Image

**Registry:** `ghcr.io/necron-99/compliance-api`  
**Tags:** `latest` (main branch), `sha-<commit>` (immutable)  
**Platforms:** `linux/amd64`, `linux/arm64`

Built automatically by GitHub Actions on push to `main` when files under
`compliance-api/` change.

To build and run locally:
```bash
cd compliance-api
docker build -t compliance-api:local .
docker run -p 8000:8000 \
  -v /path/to/compliance.db:/data/compliance.db \
  compliance-api:local
```

Visit `http://localhost:8000/docs` for the interactive API documentation.

---

## Deployment

### Prerequisites

- k3s cluster running
- cert-manager installed
- ingress-nginx installed in hostNetwork mode
- DNS: `api.compliance.robertconsulting.net` pointing to cluster IP
- AWS IAM credentials in Kubernetes Secret (see below)
- Infrastructure resources provisioned via the infrastructure repository

### First-time setup

**1. Provision infrastructure**

IAM user, DNS record, and SSM parameters are managed in the infrastructure
repository via Terraform. Run the appropriate targeted apply there first.

**2. Upload database to S3**
```bash
aws s3 cp ~/compliance.db s3://<COMPLIANCE_BUCKET>/data/compliance.db
```

**3. Create Kubernetes namespace and credentials secret**
```bash
export KUBECONFIG=~/.kube/<cluster-kubeconfig>.yaml

kubectl create namespace compliance-api

kubectl create secret generic aws-compliance-api-credentials \
  --namespace compliance-api \
  --from-literal=AWS_ACCESS_KEY_ID=<from SSM> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<from SSM> \
  --from-literal=AWS_DEFAULT_REGION=us-east-1 \
  --from-literal=S3_BUCKET=<compliance-bucket-name> \
  --from-literal=S3_KEY=data/compliance.db
```

Retrieve credential values from AWS SSM Parameter Store — paths are
documented in the infrastructure repository.

**4. Apply Kubernetes manifests**
```bash
kubectl apply -f k8s/
```

**5. Verify deployment**
```bash
# Watch pod come up
kubectl get pods -n compliance-api -w

# Check init container fetched the database
kubectl logs -n compliance-api deployment/compliance-api -c fetch-database

# Check API is running
kubectl logs -n compliance-api deployment/compliance-api -c compliance-api

# Check TLS certificate (takes 1-2 minutes)
kubectl get certificate -n compliance-api

# Test the API
curl https://api.compliance.robertconsulting.net/health
curl https://api.compliance.robertconsulting.net/stats
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

## Related Repositories

| Repository | Purpose |
|------------|---------|
| `robert-consulting-infrastructure` | Terraform — cloud infrastructure |
| `robert-consulting-content` | Website content, compliance importer |
| `robert-consulting-compliance-api` | This repo — compliance API service |

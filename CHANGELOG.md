
# Changelog

All notable changes to the Compliance Framework API are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.0.0] — 2026-05-18

### Added
- Initial production release
- FastAPI application serving the Robert Consulting compliance framework
  mapping database via REST API
- Endpoints: `/health`, `/stats`, `/frameworks`, `/frameworks/{code}`,
  `/frameworks/{code}/controls`, `/domains`, `/canonical`,
  `/controls/{id}/mappings`, `/mappings`, `/search`
- Interactive OpenAPI documentation at `/docs` and `/redoc`
- CORS support for `compliance.robertconsulting.net`
- Multi-stage Docker build — `python:3.12-slim` base, non-root user
- GitHub Actions CI/CD: build and push to `ghcr.io/necron-99/compliance-api`
  on push to `main` when `compliance-api/` files change
- Kubernetes deployment with S3 init container pattern:
  init container fetches `compliance.db` from S3 on pod start
- cert-manager ClusterIssuer for Let's Encrypt production certificates
- ingress-nginx Ingress with automatic TLS — `api.compliance.robertconsulting.net`
- AWS IAM: scoped read-only S3 access for the API pod (`GetObject` on
  `compliance.db` only)
- AWS Route53 A record managed by Terraform in infrastructure repository

### Database (v1.0.0)
- 16 frameworks: NIST 800-53, NIST CSF, NIST 800-171, NIST SSDF,
  NIST AI RMF, FedRAMP, ISO 27001, GDPR, NIS2, DORA, HIPAA,
  PCI-DSS, SOC2, CMMC, CISA CPG, SCF
- 5,518 framework controls
- 2,222 cross-framework mappings
- Sources: NIST OSCAL, FedRAMP OSCAL profiles, NIST OLIR Excel crosswalks,
  CISO Assistant community library (AGPLv3), manual GDPR/DORA mappings

---

## Versioning Policy

### Semantic versioning rules for this API

**MAJOR** version (breaking change) — increment when:
- Removing or renaming an endpoint
- Changing response field names or structure
- Changing pagination behavior in a backward-incompatible way
- Dropping support for a query parameter

**MINOR** version (new functionality) — increment when:
- Adding a new endpoint
- Adding new optional query parameters
- Adding new response fields (additive, non-breaking)
- Adding new frameworks or significantly expanding mapping coverage

**PATCH** version (bug fix / data update) — increment when:
- Fixing incorrect data in the database
- Performance improvements with no API changes
- Security patches with no API changes
- Routine database refresh (new framework data imported)

### Database versioning

The `compliance.db` file in S3 is independently versioned via S3 object
versioning. Every upload creates a new S3 version, enabling rollback to
any previous database state without redeploying the application.

To deploy a database update:
```bash
# Upload new database
aws s3 cp ~/compliance.db s3://<COMPLIANCE_BUCKET>/data/compliance.db

# Restart pod to fetch new database
kubectl rollout restart deployment/compliance-api -n compliance-api
```

To roll back a database update:
```bash
# List available versions
aws s3api list-object-versions \
  --bucket <COMPLIANCE_BUCKET> \
  --prefix data/compliance.db

# Restore a previous version
aws s3api copy-object \
  --bucket <COMPLIANCE_BUCKET> \
  --copy-source "<COMPLIANCE_BUCKET>/data/compliance.db?versionId=<VERSION_ID>" \
  --key data/compliance.db

# Restart pod
kubectl rollout restart deployment/compliance-api -n compliance-api
```

### Application versioning

The API version is set in `compliance-api/main.py`:
```python
app = FastAPI(
    version="1.0.0",  # update this on each release
    ...
)
```

Update this value and create a git tag on release:
```bash
git tag -a v1.0.0 -m "Initial production release"
git push origin v1.0.0
```

GitHub Actions automatically tags the container image with the git SHA
(`sha-<commit>`) for every push, providing immutable image references
for rollback:
```bash
# Roll back to a specific image version
kubectl set image deployment/compliance-api \
  compliance-api=ghcr.io/necron-99/compliance-api:sha-<commit> \
  -n compliance-api
```

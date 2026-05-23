# Changelog

All notable changes to the Compliance Framework API are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.2.0] — 2026-05-23

### Added
- `GET /attack/techniques/{id}` — NIST 800-53 controls that mitigate an ATT&CK technique
- `GET /attack/by-control/{control_id}` — ATT&CK techniques addressed by a NIST control
- `GET /attack/stats` — ATT&CK mapping coverage statistics
- `GET /attack/search` — search ATT&CK technique mappings
- 3,797 ATT&CK-to-NIST 800-53 mappings (CTID Mappings Explorer, ATT&CK v16.1)
- Bi-directional links to threat intelligence platform — technique IDs in compliance
  mapper now link to `threat.robertconsulting.net/#/technique/{id}`
- Prometheus metrics via `prometheus-fastapi-instrumentator`

### Changed
- Dockerfile: upgraded to multi-stage build matching threat-api pattern
  (builder + runtime stages, smaller final image)
- Dockerfile: `uvicorn` direct invocation, `--workers 1` (consistent with threat-api)
- `requirements.txt`: added `httpx==0.27.0`

### Infrastructure
- `platform-ops` submodule added
- `.gitignore` added
- GitHub Actions updated to Node.js 24 compatible action versions
- Monitoring config migrated to `robert-consulting-platform-ops` repo
- Accidental `index.html` (cached Helm website page) removed from repo root

---

## [1.1.0] — 2026-05-20

### Added
- `GET /attack/*` endpoints for ATT&CK technique cross-referencing
- ATT&CK technique mapping table and import pipeline
- `attack_technique_mappings` table in compliance DB schema

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
- Kubernetes deployment with S3 init container pattern
- 16 compliance frameworks with 6,000+ controls and 2,200+ cross-framework mappings

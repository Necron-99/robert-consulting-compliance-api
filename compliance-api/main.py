"""
compliance_api/main.py
======================
FastAPI application serving the Robert Consulting compliance framework
mapping database via REST API.

Endpoints:
    GET /health                           — liveness/readiness probe
    GET /stats                            — summary counts
    GET /frameworks                       — list all frameworks
    GET /frameworks/{code}                — single framework detail
    GET /frameworks/{code}/controls       — controls for a framework
    GET /domains                          — list all control domains
    GET /canonical                        — list canonical controls
    GET /controls/{id}/mappings           — cross-framework mappings for a control
    GET /mappings                         — all mappings (paginated)
    GET /search                           — search controls by keyword

Database:
    SQLite at DATABASE_PATH (env var, default /data/compliance.db)
    Fetched from S3 by init container on pod start.
    Read-only — all writes happen via the compliance importer tool.

CORS:
    Allowed origins configured via CORS_ORIGINS env var.
    Defaults to compliance.robertconsulting.net and robertconsulting.net.
"""

import os
import sqlite3
import logging
from contextlib import asynccontextmanager
from typing import Optional

from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# =============================================================================
# Configuration
# =============================================================================

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/compliance.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
CORS_ORIGINS_RAW = os.getenv(
    "CORS_ORIGINS",
    "https://compliance.robertconsulting.net,https://robertconsulting.net"
)
CORS_ORIGINS = [o.strip() for o in CORS_ORIGINS_RAW.split(",")]

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
log = logging.getLogger(__name__)

# =============================================================================
# Database helpers
# =============================================================================

def get_db() -> sqlite3.Connection:
    """
    Open a read-only connection to the compliance SQLite database.
    Uses URI mode with immutable=1 for safe concurrent reads.
    """
    if not os.path.exists(DATABASE_PATH):
        raise RuntimeError(
            f"Database not found at {DATABASE_PATH}. "
            "Init container may not have completed successfully."
        )
    conn = sqlite3.connect(
        f"file:{DATABASE_PATH}?mode=ro&immutable=1",
        uri=True,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a read query and return rows as a list of dicts."""
    conn = get_db()
    try:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> Optional[dict]:
    """Execute a read query and return the first row as a dict, or None."""
    conn = get_db()
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

# =============================================================================
# App lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify database is accessible on startup."""
    log.info(f"Starting compliance API — database: {DATABASE_PATH}")
    try:
        result = query_one("SELECT COUNT(*) as n FROM frameworks")
        log.info(f"Database ready — {result['n']} frameworks loaded")
    except Exception as e:
        log.error(f"Database check failed: {e}")
        raise
    yield
    log.info("Compliance API shutting down")

# =============================================================================
# FastAPI app
# =============================================================================

app = FastAPI(
    title="Robert Consulting Compliance Framework API",
    description=(
        "Cross-framework compliance control mapping API. "
        "Covers NIST 800-53, FedRAMP, ISO 27001, GDPR, NIS2, DORA, "
        "HIPAA, PCI-DSS, SOC2, CMMC, and more."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

# =============================================================================
# Health
# =============================================================================

@app.get("/health", tags=["system"])
def health():
    """Liveness and readiness probe endpoint."""
    try:
        result = query_one("SELECT COUNT(*) as n FROM frameworks")
        return {
            "status": "ok",
            "database": DATABASE_PATH,
            "frameworks": result["n"],
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")

# =============================================================================
# Stats
# =============================================================================

@app.get("/stats", tags=["overview"])
def get_stats():
    """Return summary counts for the landing page stat cards."""
    frameworks     = query_one("SELECT COUNT(*) as n FROM frameworks")
    domains        = query_one("SELECT COUNT(*) as n FROM control_domains")
    canonical      = query_one("SELECT COUNT(*) as n FROM canonical_controls")
    controls       = query_one("SELECT COUNT(*) as n FROM framework_controls")
    mappings       = query_one("SELECT COUNT(*) as n FROM mappings")
    by_relationship = query(
        "SELECT relationship, COUNT(*) as count FROM mappings GROUP BY relationship ORDER BY count DESC"
    )
    return {
        "frameworks":          frameworks["n"],
        "control_domains":     domains["n"],
        "canonical_controls":  canonical["n"],
        "framework_controls":  controls["n"],
        "cross_framework_mappings": mappings["n"],
        "mappings_by_relationship": by_relationship,
    }

# =============================================================================
# Frameworks
# =============================================================================

@app.get("/frameworks", tags=["frameworks"])
def list_frameworks():
    """List all compliance frameworks."""
    return query(
        "SELECT * FROM frameworks ORDER BY region, code"
    )


@app.get("/frameworks/{code}", tags=["frameworks"])
def get_framework(code: str):
    """Get a single framework by its code (e.g., NIST-800-53, GDPR)."""
    fw = query_one(
        "SELECT * FROM frameworks WHERE code = ?",
        (code.upper(),)
    )
    if not fw:
        raise HTTPException(status_code=404, detail=f"Framework '{code}' not found")
    return fw


@app.get("/frameworks/{code}/controls", tags=["frameworks"])
def get_framework_controls(
    code: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    include_description: bool = Query(default=False),
):
    """
    Get all controls for a framework, paginated.

    By default descriptions are excluded for performance — set
    include_description=true to include full control text.
    """
    fw = query_one("SELECT id FROM frameworks WHERE code = ?", (code.upper(),))
    if not fw:
        raise HTTPException(status_code=404, detail=f"Framework '{code}' not found")

    fw_id = fw["id"]
    offset = (page - 1) * page_size

    # Count total
    total = query_one(
        "SELECT COUNT(*) as n FROM framework_controls WHERE framework_id = ?",
        (fw_id,)
    )["n"]

    if include_description:
        cols = "id, framework_id, canonical_id, control_id, name, description, guidance, guidance_plain"
    else:
        cols = "id, framework_id, canonical_id, control_id, name, guidance_plain"

    controls = query(
        f"SELECT {cols} FROM framework_controls "
        f"WHERE framework_id = ? ORDER BY control_id "
        f"LIMIT ? OFFSET ?",
        (fw_id, page_size, offset)
    )

    return {
        "framework_code": code.upper(),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "controls": controls,
    }

# =============================================================================
# Domains
# =============================================================================

@app.get("/domains", tags=["domains"])
def list_domains():
    """List all canonical control domains."""
    return query("SELECT * FROM control_domains ORDER BY code")

# =============================================================================
# Canonical controls
# =============================================================================

@app.get("/canonical", tags=["canonical"])
def list_canonical():
    """List all canonical controls with their domain."""
    return query("""
        SELECT cc.*, cd.name as domain_name, cd.code as domain_code
        FROM canonical_controls cc
        JOIN control_domains cd ON cc.domain_id = cd.id
        ORDER BY cd.code, cc.code
    """)

# =============================================================================
# Mappings
# =============================================================================

@app.get("/controls/{control_id}/mappings", tags=["mappings"])
def get_control_mappings(
    control_id: int,
    direction: str = Query(default="both", pattern="^(source|target|both)$"),
):
    """
    Get all cross-framework mappings for a specific control (by database ID).

    direction:
        source — mappings where this control is the source
        target — mappings where this control is the target
        both   — all mappings in either direction (default)
    """
    # Verify control exists
    ctrl = query_one("SELECT * FROM framework_controls WHERE id = ?", (control_id,))
    if not ctrl:
        raise HTTPException(status_code=404, detail=f"Control ID {control_id} not found")

    base_sql = """
        SELECT
            m.id,
            m.relationship,
            m.notes,
            sf.code as source_framework,
            sc.control_id as source_control_id,
            sc.name as source_control_name,
            tf.code as target_framework,
            tc.control_id as target_control_id,
            tc.name as target_control_name
        FROM mappings m
        JOIN framework_controls sc ON m.source_control_id = sc.id
        JOIN framework_controls tc ON m.target_control_id = tc.id
        JOIN frameworks sf ON sc.framework_id = sf.id
        JOIN frameworks tf ON tc.framework_id = tf.id
    """

    if direction == "source":
        mappings = query(base_sql + " WHERE m.source_control_id = ?", (control_id,))
    elif direction == "target":
        mappings = query(base_sql + " WHERE m.target_control_id = ?", (control_id,))
    else:
        mappings = query(
            base_sql + " WHERE m.source_control_id = ? OR m.target_control_id = ?",
            (control_id, control_id)
        )

    return {
        "control": ctrl,
        "mapping_count": len(mappings),
        "mappings": mappings,
    }


@app.get("/mappings", tags=["mappings"])
def list_mappings(
    source_framework: Optional[str] = None,
    target_framework: Optional[str] = None,
    relationship: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
):
    """
    List all cross-framework mappings, with optional filtering.

    Filters:
        source_framework — e.g., NIST-800-53
        target_framework — e.g., ISO-27001
        relationship     — equivalent, subset, superset, related
    """
    where_clauses = []
    params = []

    if source_framework:
        where_clauses.append("sf.code = ?")
        params.append(source_framework.upper())
    if target_framework:
        where_clauses.append("tf.code = ?")
        params.append(target_framework.upper())
    if relationship:
        where_clauses.append("m.relationship = ?")
        params.append(relationship.lower())

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"""
        SELECT COUNT(*) as n FROM mappings m
        JOIN framework_controls sc ON m.source_control_id = sc.id
        JOIN framework_controls tc ON m.target_control_id = tc.id
        JOIN frameworks sf ON sc.framework_id = sf.id
        JOIN frameworks tf ON tc.framework_id = tf.id
        {where_sql}
    """
    total = query_one(count_sql, tuple(params))["n"]

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT
            m.id,
            m.relationship,
            m.notes,
            sf.code as source_framework,
            sc.control_id as source_control_id,
            sc.name as source_control_name,
            tf.code as target_framework,
            tc.control_id as target_control_id,
            tc.name as target_control_name
        FROM mappings m
        JOIN framework_controls sc ON m.source_control_id = sc.id
        JOIN framework_controls tc ON m.target_control_id = tc.id
        JOIN frameworks sf ON sc.framework_id = sf.id
        JOIN frameworks tf ON tc.framework_id = tf.id
        {where_sql}
        ORDER BY sf.code, sc.control_id
        LIMIT ? OFFSET ?
    """
    mappings = query(data_sql, tuple(params) + (page_size, offset))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "mappings": mappings,
    }

# =============================================================================
# Search
# =============================================================================

@app.get("/search", tags=["search"])
def search_controls(
    q: str = Query(..., min_length=2, description="Search term"),
    framework: Optional[str] = Query(default=None, description="Filter by framework code"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """
    Search controls by keyword across control_id, name, and description.

    Supports partial matching — 'access control' matches any control
    containing those words in its ID, name, or description.
    """
    search_term = f"%{q}%"
    params = [search_term, search_term, search_term]
    fw_filter = ""

    if framework:
        fw_filter = "AND f.code = ?"
        params.append(framework.upper())

    count_sql = f"""
        SELECT COUNT(*) as n
        FROM framework_controls fc
        JOIN frameworks f ON fc.framework_id = f.id
        WHERE (fc.control_id LIKE ? OR fc.name LIKE ? OR fc.description LIKE ?)
        {fw_filter}
    """
    total = query_one(count_sql, tuple(params))["n"]

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT
            fc.id,
            f.code as framework_code,
            f.name as framework_name,
            f.region,
            fc.control_id,
            fc.name,
            fc.description
        FROM framework_controls fc
        JOIN frameworks f ON fc.framework_id = f.id
        WHERE (fc.control_id LIKE ? OR fc.name LIKE ? OR fc.description LIKE ?)
        {fw_filter}
        ORDER BY f.code, fc.control_id
        LIMIT ? OFFSET ?
    """
    results = query(data_sql, tuple(params) + (page_size, offset))

    return {
        "query": q,
        "framework_filter": framework,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "results": results,
    }

# =============================================================================
# ATT&CK Technique Mappings
# =============================================================================

@app.get("/attack/techniques", tags=["attack"])
def list_attack_techniques(
    tactic: Optional[str] = Query(default=None, description="Filter by NIST control family e.g. AC, SC, IA"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
):
    """
    List all ATT&CK techniques that have NIST 800-53 mitigations.
    Optionally filter by NIST control family (tactic_group).
    """
    where = "WHERE tactic_group = ?" if tactic else ""
    params = (tactic.upper(),) if tactic else ()

    total = query_one(
        f"SELECT COUNT(DISTINCT technique_id) as n FROM attack_technique_mappings {where}",
        params
    )["n"]

    offset = (page - 1) * page_size
    results = query(
        f"""SELECT technique_id, technique_name,
               GROUP_CONCAT(DISTINCT tactic_group) as tactic_groups,
               COUNT(*) as control_count
            FROM attack_technique_mappings
            {where}
            GROUP BY technique_id, technique_name
            ORDER BY technique_id
            LIMIT ? OFFSET ?""",
        params + (page_size, offset)
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "techniques": results,
    }


@app.get("/attack/by-control/{control_id}", tags=["attack"])
def get_techniques_by_control(control_id: str):
    """Get all ATT&CK techniques mitigated by a specific NIST 800-53 control."""
    techniques = query(
        """SELECT technique_id, technique_name, tactic_group, comments
           FROM attack_technique_mappings
           WHERE nist_control_id = ?
           ORDER BY technique_id""",
        (control_id.upper(),)
    )
    return {
        "nist_control_id": control_id.upper(),
        "technique_count": len(techniques),
        "techniques": techniques,
    }


@app.get("/attack/techniques/{technique_id}", tags=["attack"])
def get_technique(technique_id: str):
    """
    Get a specific ATT&CK technique and all NIST 800-53 controls that mitigate it,
    with transitive compliance framework coverage via existing cross-framework mappings.
    """
    technique_id = technique_id.upper()

    # Get direct NIST mappings
    nist_mappings = query(
        """SELECT atm.nist_control_id, atm.tactic_group, atm.comments,
                  fc.id as fc_id, fc.name as control_name, fc.description
           FROM attack_technique_mappings atm
           LEFT JOIN framework_controls fc ON atm.nist_control_fk = fc.id
           WHERE atm.technique_id = ?
           ORDER BY atm.nist_control_id""",
        (technique_id,)
    )

    if not nist_mappings:
        raise HTTPException(
            status_code=404,
            detail=f"Technique '{technique_id}' not found or has no NIST mitigations"
        )

    technique_name = query_one(
        "SELECT technique_name FROM attack_technique_mappings WHERE technique_id = ? LIMIT 1",
        (technique_id,)
    )["technique_name"]

    # For each NIST control, get transitive framework coverage
    # Shows which other frameworks also have controls mapped to these NIST controls
    fc_ids = [m["fc_id"] for m in nist_mappings if m["fc_id"]]
    transitive_coverage = {}

    if fc_ids:
        placeholders = ",".join("?" * len(fc_ids))
        # Controls that these NIST controls map TO (outbound from NIST)
        outbound = query(
            f"""SELECT DISTINCT f.code as framework, COUNT(*) as count
                FROM mappings m
                JOIN framework_controls fc ON m.target_control_id = fc.id
                JOIN frameworks f ON fc.framework_id = f.id
                WHERE m.source_control_id IN ({placeholders})
                AND f.code != 'NIST-800-53'
                GROUP BY f.code
                ORDER BY count DESC""",
            tuple(fc_ids)
        )
        # Controls that map TO these NIST controls (inbound)
        inbound = query(
            f"""SELECT DISTINCT f.code as framework, COUNT(*) as count
                FROM mappings m
                JOIN framework_controls fc ON m.source_control_id = fc.id
                JOIN frameworks f ON fc.framework_id = f.id
                WHERE m.target_control_id IN ({placeholders})
                AND f.code != 'NIST-800-53'
                GROUP BY f.code
                ORDER BY count DESC""",
            tuple(fc_ids)
        )
        transitive_coverage = {
            "frameworks_with_mapped_controls": outbound + inbound
        }

    return {
        "technique_id": technique_id,
        "technique_name": technique_name,
        "nist_control_count": len(nist_mappings),
        "nist_controls": nist_mappings,
        "transitive_framework_coverage": transitive_coverage,
    }


@app.get("/attack/search", tags=["attack"])
def search_techniques(
    q: str = Query(..., min_length=2, description="Search technique name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Search ATT&CK techniques by name."""
    search_term = f"%{q}%"
    total = query_one(
        """SELECT COUNT(DISTINCT technique_id) as n
           FROM attack_technique_mappings
           WHERE technique_name LIKE ? OR technique_id LIKE ?""",
        (search_term, search_term)
    )["n"]

    offset = (page - 1) * page_size
    results = query(
        """SELECT technique_id, technique_name,
               GROUP_CONCAT(DISTINCT tactic_group) as tactic_groups,
               COUNT(*) as control_count
           FROM attack_technique_mappings
           WHERE technique_name LIKE ? OR technique_id LIKE ?
           GROUP BY technique_id, technique_name
           ORDER BY technique_id
           LIMIT ? OFFSET ?""",
        (search_term, search_term, page_size, offset)
    )

    return {
        "query": q,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "techniques": results,
    }


@app.get("/attack/stats", tags=["attack"])
def attack_stats():
    """Summary statistics for the ATT&CK technique mappings."""
    try:
        total = query_one(
            "SELECT COUNT(*) as n FROM attack_technique_mappings"
        )["n"]
        techniques = query_one(
            "SELECT COUNT(DISTINCT technique_id) as n FROM attack_technique_mappings"
        )["n"]
        controls = query_one(
            "SELECT COUNT(DISTINCT nist_control_id) as n FROM attack_technique_mappings"
        )["n"]
        by_family = query(
            """SELECT tactic_group, COUNT(*) as mappings,
                      COUNT(DISTINCT technique_id) as techniques
               FROM attack_technique_mappings
               GROUP BY tactic_group
               ORDER BY mappings DESC"""
        )
        return {
            "total_mappings": total,
            "unique_techniques": techniques,
            "unique_nist_controls": controls,
            "by_nist_family": by_family,
            "source": "CTID Mappings Explorer — ATT&CK 16.1 / NIST 800-53 Rev5",
            "license": "Apache 2.0",
        }
    except Exception:
        return {"total_mappings": 0, "message": "ATT&CK mappings not yet imported"}

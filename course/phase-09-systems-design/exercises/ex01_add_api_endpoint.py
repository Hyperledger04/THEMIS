"""
Phase 9 — Exercise 1: Add a /research Endpoint to the Control Plane

Use FastAPI's TestClient — no server needed to run.
# pip install fastapi httpx
"""
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
except ImportError:
    print("Install: pip install fastapi httpx")
    raise SystemExit(1)

from typing import Optional

app = FastAPI(title="LexAgent Control Plane")


# ── Existing endpoints (do not modify) ────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "lexagent-control-plane"}


class DraftRequest(BaseModel):
    matter: str
    matter_type: Optional[str] = None
    firm_id: str = "personal"


class DraftResponse(BaseModel):
    matter_id: str
    draft: str
    matter_type: str


@app.post("/draft", response_model=DraftResponse)
async def draft_endpoint(req: DraftRequest):
    """Draft a document from a matter brief."""
    return DraftResponse(
        matter_id=f"matter_{req.firm_id}_001",
        draft=f"IN THE HIGH COURT\n\nFor: {req.matter[:40]}...",
        matter_type=req.matter_type or "writ_petition",
    )


# ── TODO 1: Define request/response models for /research ──────────────────────
# ResearchRequest: query (str, required), matter_id (str, required), limit (int, default 3)
# ResearchResponse: results (list[dict]), query (str), count (int)
# Each result dict: {"title": str, "citation": str, "snippet": str}

# TODO: define ResearchRequest and ResearchResponse Pydantic models here


# ── TODO 2: Implement the /research POST endpoint ─────────────────────────────
# - Path: POST /research
# - Response model: ResearchResponse
# - Logic: call stub_search(req.query, req.limit), return results
# - If query is empty: raise HTTPException(status_code=422, detail="Query cannot be empty")

def stub_search(query: str, limit: int) -> list[dict]:
    """Do not modify."""
    cases = [
        {"title": "Maneka Gandhi v. Union of India", "citation": "AIR 1978 SC 597",
         "snippet": "Article 21 personal liberty includes right to travel abroad."},
        {"title": "Kesavananda Bharati v. State of Kerala", "citation": "AIR 1973 SC 1461",
         "snippet": "Basic structure of the Constitution cannot be amended."},
        {"title": "A.K. Gopalan v. State of Madras", "citation": "AIR 1950 SC 27",
         "snippet": "Preventive detention and the scope of Article 21."},
    ]
    return cases[:limit]

# TODO: implement the /research endpoint here


# ── TODO 3: Add a GET /matter/{matter_id} endpoint ────────────────────────────
# - Path: GET /matter/{matter_id}
# - Returns: {"matter_id": matter_id, "status": "active", "documents": 0}
# - If matter_id starts with "invalid_": raise HTTPException(404, "Matter not found")

# TODO: implement the /matter/{matter_id} endpoint here


# ── TESTS ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    client = TestClient(app)

    # Test existing endpoints
    r = client.get("/health")
    assert r.status_code == 200
    print("✓ GET /health works")

    r = client.post("/draft", json={"matter": "writ petition against demolition"})
    assert r.status_code == 200
    assert "draft" in r.json()
    print("✓ POST /draft works")

    # Test /research endpoint
    r = client.post("/research", json={"query": "article 21", "matter_id": "m001"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "results" in data, "Response must have 'results' field"
    assert "count" in data, "Response must have 'count' field"
    assert len(data["results"]) == 3, f"Expected 3 results, got {len(data['results'])}"
    assert data["results"][0]["title"] == "Maneka Gandhi v. Union of India"
    print(f"✓ POST /research works: {data['count']} results")

    # Test empty query validation
    r = client.post("/research", json={"query": "", "matter_id": "m001"})
    assert r.status_code == 422, f"Expected 422 for empty query, got {r.status_code}"
    print("✓ Empty query validation works")

    # Test /matter/{id}
    r = client.get("/matter/m001")
    assert r.status_code == 200
    assert r.json()["matter_id"] == "m001"
    print("✓ GET /matter/{matter_id} works")

    r = client.get("/matter/invalid_xyz")
    assert r.status_code == 404
    print("✓ 404 for invalid matter_id works")

    print("\n✅ All tests passed!")

# ── PAUSE AND THINK ───────────────────────────────────────────────────────────
# 1. Open lexagent/gateway/control_plane.py — what authentication does the real
#    /draft endpoint use? Is there a Depends(verify_jwt) call?
# 2. FastAPI validates request models automatically. What happens if you POST
#    {"query": 123, "matter_id": "m001"} — does it accept the integer?
#    Try it: client.post("/research", json={"query": 123, "matter_id": "m001"})
# 3. The /research endpoint here runs synchronously. In production, a research
#    call takes 30+ seconds. How would you use FastAPI BackgroundTasks to
#    return a job_id immediately and let the research run asynchronously?

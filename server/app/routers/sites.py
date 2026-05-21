from fastapi import APIRouter, HTTPException

from app.state import store

router = APIRouter(prefix="/v1/sites", tags=["sites"])


@router.get("")
def list_sites():
    return {"items": list(store.snapshot(store.sites).values())}


@router.get("/{site_id}/summary")
def site_summary(site_id: str):
    machines = store.list_machines(site_id)
    if not machines and site_id not in store.sites:
        raise HTTPException(status_code=404, detail="Site not found")
    return {
        "siteId": site_id,
        "machineCount": len(machines),
        "criticalCount": len([m for m in machines if m.get("state") == "critical"]),
        "protectedCount": len([m for m in machines if m.get("state") == "protected"]),
        "coverage": "good" if all(m.get("coverage", {}).get("state") != "offline" for m in machines) else "weak",
    }


@router.get("/{site_id}/alerts")
def list_alerts(site_id: str):
    return {"items": [a for a in store.snapshot(store.alerts) if a.get("siteId") == site_id]}


@router.get("/{site_id}/actions")
def list_actions(site_id: str):
    return {"items": [a for a in store.snapshot(store.actions) if a.get("siteId") == site_id][:50]}


@router.get("/{site_id}/impact")
def list_impact(site_id: str):
    return {"siteId": site_id, "items": store.snapshot(store.impact)}


@router.get("/{site_id}/mesh")
def mesh_status(site_id: str):
    gateways = [g for g in store.snapshot(store.mesh_gateways).values() if g.get("siteId") == site_id]
    nodes = [n for n in store.snapshot(store.mesh_nodes).values() if n.get("siteId") == site_id]
    return {"siteId": site_id, "gateways": gateways, "nodes": nodes}

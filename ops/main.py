"""
Deplyx Ops Dashboard
Lightweight monitoring dashboard for the Deplyx VPS deployment.
"""

import os
import asyncio
from datetime import datetime, timezone

import docker
import httpx
import psutil
from fastapi import FastAPI, Request, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Deplyx Ops", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

OPS_TOKEN = os.getenv("OPS_TOKEN", "changeme")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:8080")

# ── Auth ──────────────────────────────────────────────────────

def verify_token(request: Request):
    token = request.query_params.get("token") or request.cookies.get("ops_token")
    if token != OPS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token


# ── Docker client ─────────────────────────────────────────────

def get_docker():
    return docker.DockerClient(base_url="unix:///var/run/docker.sock")


# ── System info ───────────────────────────────────────────────

def get_system_info():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = psutil.getloadavg()
    cpu_count = psutil.cpu_count()
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime = datetime.now(timezone.utc) - boot

    return {
        "cpu_count": cpu_count,
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "load_1": round(load1, 2),
        "load_5": round(load5, 2),
        "load_15": round(load15, 2),
        "load_status": "critical" if load1 > cpu_count * 2 else "warning" if load1 > cpu_count else "ok",
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_percent": mem.percent,
        "ram_status": "critical" if mem.percent > 90 else "warning" if mem.percent > 75 else "ok",
        "swap_total_gb": round(swap.total / (1024**3), 1),
        "swap_used_gb": round(swap.used / (1024**3), 1),
        "swap_percent": swap.percent if swap.total > 0 else 0,
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_status": "critical" if disk.percent > 90 else "warning" if disk.percent > 80 else "ok",
        "uptime_days": uptime.days,
        "uptime_hours": uptime.seconds // 3600,
    }


# ── Container info ────────────────────────────────────────────

def get_containers():
    client = get_docker()
    containers = []
    for c in client.containers.list(all=True):
        # Calculate uptime
        started = c.attrs.get("State", {}).get("StartedAt", "")
        health = c.attrs.get("State", {}).get("Health", {}).get("Status", "n/a")

        # Get resource stats (non-streaming)
        try:
            stats = c.stats(stream=False)
            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            sys_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            cpu_pct = round((cpu_delta / sys_delta) * stats["cpu_stats"]["online_cpus"] * 100, 1) if sys_delta > 0 else 0
            mem_usage = round(stats["memory_stats"].get("usage", 0) / (1024**2), 1)
            mem_limit = round(stats["memory_stats"].get("limit", 0) / (1024**3), 2)
        except Exception:
            cpu_pct = 0
            mem_usage = 0
            mem_limit = 0

        containers.append({
            "name": c.name,
            "status": c.status,
            "health": health,
            "image": c.image.tags[0] if c.image.tags else c.image.short_id,
            "started": started[:19].replace("T", " ") if started else "n/a",
            "cpu_pct": cpu_pct,
            "mem_mb": mem_usage,
            "mem_limit_gb": mem_limit,
            "is_deplyx": c.name.startswith("deplyx-"),
            "is_lab": c.name.startswith("lab-"),
        })

    # Sort: deplyx first, then lab, then others
    containers.sort(key=lambda x: (0 if x["is_deplyx"] else 1 if x["is_lab"] else 2, x["name"]))
    return containers


# ── App health probes ─────────────────────────────────────────

async def check_health(url: str, timeout: float = 5.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return {
                "url": url,
                "status": resp.status_code,
                "ok": resp.status_code < 400,
                "body": resp.text[:200],
                "latency_ms": round(resp.elapsed.total_seconds() * 1000),
            }
    except Exception as e:
        return {
            "url": url,
            "status": 0,
            "ok": False,
            "body": str(e)[:200],
            "latency_ms": -1,
        }


async def get_app_health():
    backend, frontend = await asyncio.gather(
        check_health(f"{BACKEND_URL}/health"),
        check_health(f"{FRONTEND_URL}/"),
    )
    return {"backend": backend, "frontend": frontend}


# ── Routes ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, token: str = Depends(verify_token)):
    system = get_system_info()
    containers = get_containers()
    health = await get_app_health()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "system": system,
        "containers": containers,
        "health": health,
        "token": token,
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    })


@app.get("/api/system", dependencies=[Depends(verify_token)])
async def api_system():
    return get_system_info()


@app.get("/api/containers", dependencies=[Depends(verify_token)])
async def api_containers():
    return get_containers()


@app.get("/api/health", dependencies=[Depends(verify_token)])
async def api_health():
    return await get_app_health()


@app.get("/htmx/system", response_class=HTMLResponse, dependencies=[Depends(verify_token)])
async def htmx_system(request: Request):
    system = get_system_info()
    return templates.TemplateResponse("partials/system.html", {"request": request, "system": system})


@app.get("/htmx/containers", response_class=HTMLResponse, dependencies=[Depends(verify_token)])
async def htmx_containers(request: Request):
    containers = get_containers()
    return templates.TemplateResponse("partials/containers.html", {"request": request, "containers": containers})


@app.get("/htmx/health", response_class=HTMLResponse, dependencies=[Depends(verify_token)])
async def htmx_health(request: Request):
    health = await get_app_health()
    return templates.TemplateResponse("partials/health.html", {"request": request, "health": health})


@app.get("/htmx/logs", response_class=HTMLResponse, dependencies=[Depends(verify_token)])
async def htmx_logs(request: Request, container: str = Query(...), lines: int = Query(100)):
    client = get_docker()
    try:
        c = client.containers.get(container)
        logs = c.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
    except Exception as e:
        logs = f"Error: {e}"
    return templates.TemplateResponse("partials/logs.html", {
        "request": request,
        "container_name": container,
        "logs": logs,
    })


@app.get("/logs/stream", dependencies=[Depends(verify_token)])
async def stream_logs(container: str = Query(...)):
    """SSE endpoint for live container logs."""
    client = get_docker()
    c = client.containers.get(container)

    async def event_stream():
        for line in c.logs(stream=True, follow=True, tail=50, timestamps=True):
            text = line.decode("utf-8", errors="replace").strip()
            yield f"data: {text}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

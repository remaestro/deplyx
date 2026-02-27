from app.api.router import router as main_router
from app_lab.routers.lab import router as lab_router


def _paths(router):
    return {route.path for route in router.routes}


def test_main_api_router_excludes_lab_routes():
    assert all(not path.startswith('/lab') for path in _paths(main_router))


def test_lab_router_exposes_lab_routes():
    assert any(path.startswith('/v1/lab') for path in _paths(lab_router))

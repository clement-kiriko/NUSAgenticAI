import time

from monitoring.helpers import record_http_request


async def record_http_metrics(request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started_at
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    status_code = str(response.status_code)
    method = request.method
    record_http_request(method=method, path=path, status_code=status_code, duration_seconds=duration)
    return response

from __future__ import annotations

from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.routing import Route

PrincipalResolver = Callable[[Any], Awaitable[dict[str, Any] | None]]

def project_codex_maintenance_routes(adapter: Any, principal_resolver: PrincipalResolver) -> list[Route]:
    async def resolve(request: Any) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        principal = await principal_resolver(request)
        if not principal or not principal.get("identity_verified"):
            return None, JSONResponse({"status": "project_owner_login_required"}, status_code=401)
        if principal.get("project_id") != adapter.project_id or principal.get("role") != "owner_admin":
            return None, JSONResponse({"status": "project_owner_role_required"}, status_code=403)
        return principal, None

    async def context(request: Any) -> JSONResponse:
        principal, denial = await resolve(request)
        if denial:
            return denial
        return JSONResponse(adapter.masked_context(
            user_id=str(principal["user_id"]), identity_verified=True, role="owner_admin",
            business={}, technical={},
        ))

    async def create_job(request: Any) -> JSONResponse:
        principal, denial = await resolve(request)
        if denial:
            return denial
        payload = await request.json()
        try:
            result = adapter.create_job(
                user_id=str(principal["user_id"]), identity_verified=True, role="owner_admin",
                request_text=str(payload.get("request", "")),
            )
        except ValueError as exc:
            return JSONResponse({"status": "invalid_request", "detail": str(exc)}, status_code=400)
        return JSONResponse(result, status_code=201)

    async def record_result(request: Any) -> JSONResponse:
        principal, denial = await resolve(request)
        if denial:
            return denial
        payload = await request.json()
        try:
            result = adapter.record_result(
                user_id=str(principal["user_id"]), identity_verified=True, role="owner_admin",
                job_id=str(request.path_params["job_id"]), status=str(payload.get("status", "")),
                summary=str(payload.get("summary", "")),
                evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
            )
        except (ValueError, LookupError) as exc:
            return JSONResponse({"status": "invalid_result", "detail": str(exc)}, status_code=400)
        return JSONResponse(result)

    return [
        Route("/api/technical/codex/context", context, methods=["GET"]),
        Route("/api/technical/codex/jobs", create_job, methods=["POST"]),
        Route("/api/technical/codex/jobs/{job_id:str}/result", record_result, methods=["POST"]),
    ]

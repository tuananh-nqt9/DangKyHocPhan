"""FastAPI application entrypoint, per-worker lifespan, strict CORS, and v3.0 error envelopes."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from redis import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from app.api.routers import (
    admin,
    auth,
    course_classes,
    health,
    payments,
    queue,
    registrations,
    sso,
)
from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode, build_error_envelope, map_pydantic_errors
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimiter
from app.db.pool import DatabaseManager
from app.services.auth_service import AuthService
from app.services.course_class_service import CourseClassService
from app.services.health_service import HealthService
from app.services.idempotency_service import IdempotencyService
from app.services.payment_service import PaymentService
from app.services.queue_service import QueueService
from app.services.registration_service import RegistrationService
from app.services.sso_service import SsoService

CORS_ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
CORS_ALLOW_HEADERS = "Authorization, Content-Type, Idempotency-Key, X-Queue-Token"
CORS_EXPOSE_HEADERS = "X-Request-ID, Retry-After, Idempotent-Replayed"
SWAGGER_DOCS_URL = "/docs"
SWAGGER_HIDE_APP_VERSION_STYLE = (
    "<style>"
    ".swagger-ui .info .title small:not(.version-stamp) { display: none; }"
    "</style>"
)
IDEMPOTENT_PATHS = frozenset(
    {
        "/api/v1/register",
        "/api/v1/registrations/{registration_id}",
        "/api/v1/payments",
    }
)


def _apply_cors_and_standard_headers(
    request: Request,
    response: Response,
    settings: Settings,
) -> None:
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    allowed_origins = settings.allowed_origins_list

    # Always vary by Origin so shared caches / proxies never mix CORS responses
    existing_vary = response.headers.get("Vary", "")
    if "Origin" not in existing_vary:
        response.headers["Vary"] = f"{existing_vary}, Origin".lstrip(", ") if existing_vary else "Origin"

    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = CORS_EXPOSE_HEADERS

    if request.url.path.startswith(settings.api_v1_prefix):
        response.headers["Cache-Control"] = "no-store"

    effective_req_id = str(
        getattr(request.state, "effective_request_id", None)
        or getattr(request.state, "request_id", "")
    )
    if effective_req_id:
        response.headers["X-Request-ID"] = effective_req_id


def _compute_allowed_methods(app: FastAPI, scope: dict[str, Any]) -> str:
    methods: set[str] = set()
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.PARTIAL and getattr(route, "methods", None):
            methods.update(route.methods)
    if methods:
        methods.add("OPTIONS")
    return ", ".join(sorted(methods)) if methods else CORS_ALLOW_METHODS


def create_app(
    settings: Settings | None = None,
    *,
    redis_override: Redis | None = None,
    sso_service_override: SsoService | None = None,
) -> FastAPI:
    """Create a configured FastAPI application instance.

    Each worker initializes its own `psycopg_pool` inside `lifespan` (never before fork/spawn).
    """
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)
    logger = get_logger("dkhp.http")

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        db_manager = DatabaseManager(cfg)
        db_manager.open()

        owned_redis: Redis | None = None
        active_redis: Redis | None = redis_override
        if active_redis is None and (
            cfg.queue_enabled or cfg.rate_limit_backend == "redis"
        ):
            owned_redis = Redis.from_url(
                cfg.redis_url,
                socket_timeout=cfg.redis_socket_timeout_seconds,
                socket_connect_timeout=cfg.redis_socket_timeout_seconds,
                decode_responses=False,
            )
            active_redis = owned_redis

        queue_service = QueueService(cfg, redis_client=active_redis)
        idempotency_service = IdempotencyService(db_manager, cfg)
        auth_service = AuthService(db_manager, cfg, queue_service)
        sso_service = sso_service_override or SsoService(db_manager, cfg, auth_service)
        course_class_service = CourseClassService(db_manager, cfg)
        registration_service = RegistrationService(
            db_manager,
            cfg,
            idempotency_service,
            queue_service,
        )
        payment_service = PaymentService(db_manager, cfg, idempotency_service)
        health_service = HealthService(db_manager, cfg, queue_service)
        rate_limiter = RateLimiter(cfg, redis_client=active_redis)

        app_instance.state.settings = cfg
        app_instance.state.db = db_manager
        app_instance.state.redis = active_redis
        app_instance.state.queue_service = queue_service
        app_instance.state.idempotency_service = idempotency_service
        app_instance.state.auth_service = auth_service
        app_instance.state.sso_service = sso_service
        app_instance.state.course_class_service = course_class_service
        app_instance.state.registration_service = registration_service
        app_instance.state.payment_service = payment_service
        app_instance.state.health_service = health_service
        app_instance.state.rate_limiter = rate_limiter

        try:
            yield
        finally:
            if owned_redis is not None:
                try:
                    owned_redis.close()
                except Exception:
                    pass
            db_manager.close()

    app = FastAPI(
        title="Hệ thống Đăng ký Học phần Trực tuyến",
        description=(
            "API hỗ trợ đăng nhập, tra cứu lớp học phần, đăng ký và hủy đăng ký học phần. "
            "Tài liệu cung cấp thông tin đầu vào, kết quả trả về và cách xác thực cho từng chức năng."
        ),
        version=cfg.api_version,
        docs_url=None,
        lifespan=lifespan,
    )
    app.state.settings = cfg

    if app.openapi_url:
        oauth2_redirect_url = app.swagger_ui_oauth2_redirect_url

        async def custom_swagger_ui_html(req: Request) -> HTMLResponse:
            root_path = req.scope.get("root_path", "").rstrip("/")
            openapi_url = root_path + (app.openapi_url or "")
            resolved_oauth2_redirect_url = (
                root_path + oauth2_redirect_url if oauth2_redirect_url else None
            )
            base_html = get_swagger_ui_html(
                openapi_url=openapi_url,
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=resolved_oauth2_redirect_url,
                init_oauth=app.swagger_ui_init_oauth,
                swagger_ui_parameters=app.swagger_ui_parameters,
            )
            html_content = bytes(base_html.body).decode("utf-8").replace(
                "</head>",
                f"    {SWAGGER_HIDE_APP_VERSION_STYLE}\n    </head>",
                1,
            )
            return HTMLResponse(content=html_content, status_code=base_html.status_code)

        app.add_route(SWAGGER_DOCS_URL, custom_swagger_ui_html, include_in_schema=False)

        if oauth2_redirect_url:

            async def swagger_ui_redirect(req: Request) -> HTMLResponse:
                return get_swagger_ui_oauth2_redirect_html()

            app.add_route(
                oauth2_redirect_url,
                swagger_ui_redirect,
                include_in_schema=False,
            )

    @app.middleware("http")
    async def request_context_cors_and_logging_middleware(
        request: Request,
        call_next: Any,
    ) -> Response:
        start_perf = time.perf_counter()
        attempt_id = str(uuid.uuid4())
        request.state.attempt_id = attempt_id
        request.state.request_id = attempt_id
        request.state.effective_request_id = attempt_id
        request.state.idempotent_replayed = False
        request.state.response_code = ""

        # Handle valid CORS preflight OPTIONS BEFORE Bearer auth -> 204 No Content without body
        if request.method.upper() == "OPTIONS":
            origin = (request.headers.get("origin") or "").strip().rstrip("/")
            acrm = (request.headers.get("access-control-request-method") or "").strip().upper()
            if origin and origin in cfg.allowed_origins_list and acrm in {
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS",
            }:
                preflight_resp = Response(status_code=204)
                preflight_resp.headers["Access-Control-Allow-Origin"] = origin
                preflight_resp.headers["Access-Control-Allow-Methods"] = CORS_ALLOW_METHODS
                preflight_resp.headers["Access-Control-Allow-Headers"] = CORS_ALLOW_HEADERS
                preflight_resp.headers["Access-Control-Expose-Headers"] = CORS_EXPOSE_HEADERS
                preflight_resp.headers["Access-Control-Max-Age"] = "600"
                preflight_resp.headers["Vary"] = "Origin"
                preflight_resp.headers["X-Request-ID"] = attempt_id
                return preflight_resp

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(
                "Unhandled exception caught at HTTP middleware boundary.",
                extra={
                    "structured": {
                        "attempt_id": attempt_id,
                        "method": request.method,
                        "path": request.url.path,
                        "exc_type": type(exc).__name__,
                    }
                },
            )
            request.state.response_code = str(ErrorCode.INTERNAL_ERROR)
            response = JSONResponse(
                status_code=500,
                content=build_error_envelope(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Đã xảy ra lỗi hệ thống nội bộ. Vui lòng kiểm tra lại với mã request_id.",
                    request_id=attempt_id,
                ),
            )

        _apply_cors_and_standard_headers(request, response, cfg)

        latency_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)
        route_obj = request.scope.get("route")
        route_template = getattr(route_obj, "path", request.url.path)
        caller_info = getattr(request.state, "caller", None)

        logger.info(
            "HTTP request processed",
            extra={
                "structured": {
                    "request_id": str(request.state.effective_request_id),
                    "attempt_id": attempt_id,
                    "replayed": bool(request.state.idempotent_replayed),
                    "method": request.method,
                    "route": route_template,
                    "status_code": response.status_code,
                    "response_code": str(request.state.response_code),
                    "latency_ms": latency_ms,
                    "actor": caller_info["student_id"] if isinstance(caller_info, dict) else None,
                }
            },
        )
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        req_id = str(getattr(request.state, "request_id", "") or uuid.uuid4())
        request.state.response_code = str(exc.code)
        resp = JSONResponse(
            status_code=exc.status_code,
            content=build_error_envelope(
                code=exc.code,
                message=exc.message,
                request_id=req_id,
                errors=exc.errors,
            ),
            headers=dict(exc.headers),
        )
        _apply_cors_and_standard_headers(request, resp, cfg)
        return resp

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = str(getattr(request.state, "request_id", "") or uuid.uuid4())
        raw_errors = list(exc.errors())
        if any(err.get("type") == "json_invalid" for err in raw_errors):
            request.state.response_code = str(ErrorCode.INVALID_JSON)
            resp = JSONResponse(
                status_code=400,
                content=build_error_envelope(
                    code=ErrorCode.INVALID_JSON,
                    message="Cú pháp JSON không hợp lệ.",
                    request_id=req_id,
                ),
            )
        else:
            mapped_errors = map_pydantic_errors(raw_errors)
            request.state.response_code = str(ErrorCode.VALIDATION_ERROR)
            resp = JSONResponse(
                status_code=400,
                content=build_error_envelope(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Dữ liệu không hợp lệ.",
                    request_id=req_id,
                    errors=mapped_errors,
                ),
            )
        _apply_cors_and_standard_headers(request, resp, cfg)
        return resp

    @app.exception_handler(StarletteHTTPException)
    async def handle_starlette_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        req_id = str(getattr(request.state, "request_id", "") or uuid.uuid4())
        headers = dict(exc.headers or {})
        if exc.status_code == 404:
            code = ErrorCode.ENDPOINT_NOT_FOUND
            message = "Đường dẫn API không tồn tại."
        elif exc.status_code == 405:
            code = ErrorCode.METHOD_NOT_ALLOWED
            message = "Phương thức HTTP không được hỗ trợ cho đường dẫn này."
            if "Allow" not in headers and "allow" not in headers:
                headers["Allow"] = _compute_allowed_methods(app, request.scope)
        elif exc.status_code == 401:
            code = ErrorCode.UNAUTHORIZED
            message = "Chưa xác thực hoặc phiên không hợp lệ."
            headers.setdefault("WWW-Authenticate", "Bearer")
        elif exc.status_code == 415:
            code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
            message = "Kiểu dữ liệu Content-Type không được hỗ trợ."
        else:
            code = ErrorCode.INTERNAL_ERROR
            message = "Yêu cầu không thể xử lý."

        request.state.response_code = str(code)
        resp = JSONResponse(
            status_code=exc.status_code,
            content=build_error_envelope(
                code=code,
                message=message,
                request_id=req_id,
            ),
            headers=headers,
        )
        _apply_cors_and_standard_headers(request, resp, cfg)
        return resp

    # Register all 19 Spec v3.0 endpoints under `/api/v1`
    prefix = cfg.api_v1_prefix
    app.include_router(auth.public_auth_router, prefix=prefix)
    app.include_router(auth.protected_auth_router, prefix=prefix)
    app.include_router(sso.router, prefix=prefix)
    app.include_router(course_classes.router, prefix=prefix)
    app.include_router(registrations.router, prefix=prefix)
    app.include_router(payments.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(queue.router, prefix=prefix)
    app.include_router(health.router, prefix=prefix)

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("info", {})["x-spec-version"] = cfg.spec_version
        # Remove FastAPI's default 422 HTTPValidationError from routes where 422 is not used;
        # we return 400 VALIDATION_ERROR per Spec v3.0 and reserve 422 strictly for IDEMPOTENCY_KEY_REUSED.
        paths = schema.get("paths", {})
        for path_key, path_item in paths.items():
            for method_key, op in path_item.items():
                if not isinstance(op, dict):
                    continue
                responses = op.get("responses", {})
                if path_key not in IDEMPOTENT_PATHS or method_key.lower() == "get":
                    responses.pop("422", None)
        components = schema.get("components", {}).get("schemas", {})
        components.pop("HTTPValidationError", None)
        components.pop("ValidationError", None)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()

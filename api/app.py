# ruff: noqa: B008
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from packages.contracts.models import (
    FiscalYear,
    NodeApiResponse,
    ProblemDetails,
    SearchApiResponse,
    TreeCollectionApiResponse,
)

from .dependencies import get_budget_service
from .service import (
    BudgetService,
    NodeNotFound,
    PublishedDataError,
    PublishedReleaseNotFound,
)
from .settings import ApiSettings

LegalStage = Literal["PLF", "LFI"]


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved_settings = settings or ApiSettings()
    app = FastAPI(
        title="Budget France API",
        version=resolved_settings.app_version,
        description="Données budgétaires publiées, déterministes et sourcées.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = _request_id(request)
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response

    @app.exception_handler(NodeNotFound)
    async def node_not_found(request: Request, _error: NodeNotFound) -> JSONResponse:
        return _problem(
            request,
            404,
            "Nœud introuvable",
            "Le nœud demandé n'existe pas dans cette release.",
        )

    @app.exception_handler(PublishedReleaseNotFound)
    async def release_not_found(
        request: Request, _error: PublishedReleaseNotFound
    ) -> JSONResponse:
        return _problem(
            request,
            404,
            "Release introuvable",
            "Aucune release publiée ne correspond aux paramètres demandés.",
        )

    @app.exception_handler(PublishedDataError)
    async def published_data_error(request: Request, error: PublishedDataError) -> JSONResponse:
        return _problem(request, 503, "Données publiées indisponibles", str(error))

    @app.get("/healthz", tags=["system"])
    async def healthz() -> Mapping[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    async def readyz(service: BudgetService = Depends(get_budget_service)) -> Mapping[str, str]:
        del service
        return {"status": "ready"}

    @app.get("/api/v1/tree", response_model=TreeCollectionApiResponse, tags=["budget"])
    async def tree(
        request: Request,
        fiscal_year: FiscalYear = Query(default=FiscalYear.Y2026),
        legal_stage: LegalStage = Query(default="PLF"),
        service: BudgetService = Depends(get_budget_service),
    ) -> TreeCollectionApiResponse:
        data = service.tree(fiscal_year=int(fiscal_year), legal_stage=legal_stage)
        return TreeCollectionApiResponse(data=data, request_id=_request_id(request))

    @app.get("/api/v1/search", response_model=SearchApiResponse, tags=["budget"])
    async def search(
        request: Request,
        q: str = Query(min_length=1, max_length=120),
        fiscal_year: FiscalYear = Query(default=FiscalYear.Y2026),
        legal_stage: LegalStage = Query(default="PLF"),
        limit: int = Query(default=50, ge=1, le=100),
        service: BudgetService = Depends(get_budget_service),
    ) -> SearchApiResponse:
        data = service.search(
            query=q,
            fiscal_year=int(fiscal_year),
            legal_stage=legal_stage,
            limit=limit,
        )
        return SearchApiResponse(data=data, request_id=_request_id(request))

    @app.get("/api/v1/nodes/{node_id}", response_model=NodeApiResponse, tags=["budget"])
    async def node(
        node_id: UUID,
        request: Request,
        fiscal_year: FiscalYear = Query(default=FiscalYear.Y2026),
        legal_stage: LegalStage = Query(default="PLF"),
        service: BudgetService = Depends(get_budget_service),
    ) -> NodeApiResponse:
        data = service.node(
            node_id=node_id,
            fiscal_year=int(fiscal_year),
            legal_stage=legal_stage,
        )
        return NodeApiResponse(data=data, request_id=_request_id(request))

    return app


def _request_id(request: Request) -> UUID:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, UUID):
        return existing
    raw = request.headers.get("x-request-id")
    if raw:
        try:
            return UUID(raw)
        except ValueError:
            pass
    return uuid4()


def _problem(request: Request, status: int, title: str, detail: str) -> JSONResponse:
    request_id = _request_id(request)
    problem = ProblemDetails(status=status, title=title, detail=detail)
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
        headers={"X-Request-ID": str(request_id)},
    )


app = create_app()

from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, text

from .database import database_url, make_engine, migrate, sessions
from .importer import DuplicateImport, SOURCE, batch_info, import_file
from .limits import UploadSizeLimitMiddleware
from .metrics import chart_data, summarize
from .models import DailyRecord, ImportBatch
from .parsing import ImportProblem, MAX_BYTES
from .forecasting import ForecastProblem
from .forecast_service import forecast_router
from .decision_service import decision_router
from .decision_limits import DecisionBodyLimitMiddleware
from .impact_service import impact_router
from .impact_limits import ImpactBodyLimitMiddleware
from .config import Settings
from .security import SecurityMiddleware
from .database import ROOT


def create_app(url=None):
    settings = Settings.from_env()
    if settings.public:
        if url is not None:
            raise ValueError("PUBLIC_DEMO does not accept a database override.")
        from .demo import readonly_url, validate_demo
        validate_demo()
        engine = make_engine(readonly_url(), readonly=True)
    else:
        engine = make_engine(url or database_url())
    factory = sessions(engine)

    @asynccontextmanager
    async def lifespan(_):
        if not settings.public:
            migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(title="MealLoop OS API", version="0.5.0", lifespan=lifespan,
                  docs_url=None if settings.public else "/docs",
                  redoc_url=None if settings.public else "/redoc",
                  openapi_url=None if settings.public else "/openapi.json")
    app.state.engine = engine
    app.state.settings = settings
    if not settings.public:
        app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:15173", "http://127.0.0.1:15173"],
            allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.add_middleware(UploadSizeLimitMiddleware)
    app.add_middleware(DecisionBodyLimitMiddleware)
    app.add_middleware(ImpactBodyLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.hosts))
    app.add_middleware(SecurityMiddleware, settings=settings, routes=app.router.routes)

    @app.exception_handler(Exception)
    async def unexpected_error(_, exc):
        import logging
        logging.getLogger("mealloop").error("Unhandled request exception (%s)", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": {"message": "The service could not complete this request. Please retry."}},
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Do not echo raw inputs/context: NaN/Infinity are not JSON-safe and
        # submitted values need not be disclosed to explain validation failures.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]})

    @app.exception_handler(ForecastProblem)
    async def forecast_error(_, exc):
        return JSONResponse(status_code=422, content={"detail": {"message": str(exc)}})

    app.include_router(forecast_router(factory))
    app.include_router(decision_router(factory, public_demo=settings.public))
    app.include_router(impact_router(factory, public_demo=settings.public))

    @app.get("/api/config")
    def configuration():
        return {"mode": settings.mode, "version": "0.5.0", "read_only": settings.public,
                "notice": "Public demo: official historical measurements and synthetic scenarios only. Previews are never saved." if settings.public
                else "Local workspace: imports and saved records stay in this workspace."}

    @app.exception_handler(ImportProblem)
    async def import_error(_, exc):
        return JSONResponse(status_code=409 if isinstance(exc, DuplicateImport) else 422,
            content={"detail": {"message": str(exc), "errors": exc.errors}})

    @app.get("/api/health")
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "version": "0.5.0"} if settings.public else {"status": "ok", "database": "connected", "version": "0.5.0"}

    @app.get("/api/dataset/status")
    def status():
        with factory() as session:
            batches = session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
            return {"status": "ready" if batches else "empty", "official_source": SOURCE,
                "batches": [batch_info(session, batch) for batch in batches],
                "active_batch_id": batches[0].id if batches else None}

    @app.post("/api/dataset/import", status_code=201)
    def upload(file: Annotated[UploadFile, File()], source_kind: Annotated[Literal["measured", "synthetic"], Form()] = "measured",
               baseline_days: Annotated[int | None, Form(ge=0, le=10_000)] = None):
        try:
            content = file.file.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise HTTPException(413, detail={"message": "File exceeds the 10 MiB limit."})
            with factory() as session:
                batch = import_file(session, content, file.filename or "", source_kind, baseline_days)
                return batch_info(session, batch)
        finally:
            file.file.close()

    def load(session, batch_id):
        batch = session.get(ImportBatch, batch_id) if batch_id else session.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
        if batch is None:
            raise HTTPException(404, detail={"message": "Import a dataset first, or select an existing batch."})
        records = session.scalars(select(DailyRecord).where(DailyRecord.batch_id == batch.id).order_by(DailyRecord.day_index)).all()
        return batch, records

    @app.get("/api/overview")
    def overview(batch_id: Annotated[int | None, Query(gt=0)] = None):
        with factory() as session:
            batch, records = load(session, batch_id)
            periods = [{"phase": phase, **summarize([r for r in records if r.phase == phase])}
                       for phase in ("baseline", "intervention") if any(r.phase == phase for r in records)]
            return {"batch": batch_info(session, batch), "metrics": summarize(records), "periods": periods,
                "interpretation": "Descriptive comparison only. The original intervention involved artist-designed solutions; no causal effect is attributed to MealLoop OS."}

    @app.get("/api/charts")
    def charts(batch_id: Annotated[int | None, Query(gt=0)] = None):
        with factory() as session:
            batch, records = load(session, batch_id)
            return {"batch_id": batch.id, **chart_data(records)}

    dist = ROOT / "frontend/dist"
    if settings.public and not (dist / "index.html").is_file():
        raise ValueError("PUBLIC_DEMO requires the compiled frontend. Run npm --prefix frontend run build.")
    if (dist / "index.html").is_file():
        if not settings.public:
            @app.get("/template.csv", include_in_schema=False)
            def csv_template():
                return FileResponse(dist / "template.csv", media_type="text/csv", filename="mealloop-import-template.csv")

        @app.get("/", include_in_schema=False)
        @app.get("/index.html", include_in_schema=False)
        def index():
            return FileResponse(dist / "index.html")

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon():
            return FileResponse(dist / "favicon.svg")

        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    return app


app = create_app()

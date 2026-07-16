from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.limiter import limiter
import logging
import os
import sys

from app.routes import auth_router, music_router, analyze_router, recommend_router, ab_router, admin_router
from app.routes import spotify_router
from app.routes import folder_router
from app.database import get_settings

# Prevent numerical libraries from spawning multiple threads and starving the event loop
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# Database schema is owned by Alembic — see backend/alembic/versions/.
# Run `alembic upgrade head` before starting the server (done automatically
# in Docker via the CMD in backend/Dockerfile).
#
# We intentionally do NOT call Base.metadata.create_all() here because it
# would silently mask schema drift between the models and the migrations.

# Logging — use JSON in production for log aggregators, plain in dev
if os.getenv("ENVIRONMENT", "development").lower() in ("production", "staging"):
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
else:
    logging.basicConfig(
        level=logging.DEBUG if get_settings().debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

logger = logging.getLogger(__name__)
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Audio-Based Music Recommender API",
    description="API for music recommendation based on audio feature analysis",
    version="1.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware configuration
# Methods are explicit (not "*") so that allow_credentials=True is well-defined
# per the CORS spec.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",        # nginx (production, port 80)
        "http://127.0.0.1",        # nginx (production, port 80)
        "http://localhost:80",
        "http://localhost:3000",   # React dev server (legacy)
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ],
    expose_headers=["Content-Disposition"],
    max_age=600,
)

# Rate limiter — attach to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Register routers
app.include_router(auth_router)
app.include_router(music_router)
app.include_router(spotify_router)
app.include_router(analyze_router)
app.include_router(recommend_router)
app.include_router(ab_router)
app.include_router(admin_router)
app.include_router(folder_router)


# Serve static frontend in production if built
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(STATIC_DIR):
    STATIC_DIR = "/app/static"

if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str = ""):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        
        raise HTTPException(status_code=404, detail="Not found")
else:
    @app.get("/")
    def root():
        """Root endpoint - API health check."""
        return {
            "message": "Audio-Based Music Recommender API",
            "version": "1.1.0",
            "status": "running",
            "docs": "/api/docs",
        }


@app.get("/api/health")
def health_check():
    """Liveness probe — does NOT touch the DB.  See /api/ready for that."""
    return {"status": "healthy"}


@app.get("/api/ready")
def readiness_check():
    """
    Readiness probe — confirms DB connectivity.  Used by Docker healthcheck
    and orchestrators to decide when traffic should be routed.
    """
    from sqlalchemy import text
    from app.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Readiness check failed: %s", str(e))
        return {"status": "unready", "detail": "database unreachable"}
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.debug)

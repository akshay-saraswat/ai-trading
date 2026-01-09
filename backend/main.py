"""
Main FastAPI application entry point.

This file orchestrates:
- FastAPI app initialization
- Middleware configuration
- Route registration
- WebSocket endpoint registration
- Application lifecycle (startup/shutdown)

Clean separation of concerns:
- api/routes.py: HTTP endpoints
- api/websocket.py: WebSocket handlers
- api/models.py: Pydantic schemas
- services/trading_service.py: Business logic
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .services.trading_service import trading_service
from .api.routes import router
from .api.websocket import websocket_endpoint

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ========== LIFECYCLE MANAGEMENT ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown:
    - Connects to cache and database
    - Logs in to Robinhood (if credentials provided)
    - Starts background position monitoring
    - Cleans up on shutdown
    """
    # Startup
    logger.info("🚀 Starting AI Trading Bot v2...")
    await trading_service.start()
    logger.info("✅ Trading Service v2 started")

    yield

    # Shutdown
    logger.info("👋 Shutting down AI Trading Bot v2...")
    await trading_service.shutdown()
    logger.info("✅ Trading Service v2 shutdown complete")


# ========== APP INITIALIZATION ==========

app = FastAPI(
    title="AI Trading Bot v2 - Production",
    version="2.0.0",
    description="Production-ready options trading bot with async architecture",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== ROUTE REGISTRATION ==========

# Register HTTP routes
app.include_router(router)

# Register WebSocket endpoint
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat and updates"""
    await websocket_endpoint(websocket)


# ========== DEV SERVER ==========

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)

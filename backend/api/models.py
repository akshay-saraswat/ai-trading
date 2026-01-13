"""
Pydantic models for API request/response validation.
"""
from pydantic import BaseModel
from typing import Optional, Dict


class ChatMessage(BaseModel):
    """Chat message from client"""
    message: str
    session_id: Optional[str] = None


class Position(BaseModel):
    """Position model for API responses"""
    position_id: str
    ticker: str
    decision: str
    entry_price: float
    current_price: Optional[float]
    pct_change: Optional[float]
    strike: str
    expiration: str
    contracts: int
    take_profit: Optional[float]
    stop_loss: Optional[float]
    started_at: Optional[str]
    source: str = 'bot'
    strategy_used: Optional[str] = 'none'


class UpdateTPSLRequest(BaseModel):
    """Request to update take profit or stop loss"""
    value: float


class Settings(BaseModel):
    """User settings for indicators, strategies, and risk management"""
    indicators: Dict[str, bool]
    strategies: Dict[str, bool]
    riskManagement: Dict[str, float]

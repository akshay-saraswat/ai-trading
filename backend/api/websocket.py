"""
WebSocket endpoint for real-time chat and ticker analysis.

Handles:
- Client connections/disconnections
- Ticker analysis requests
- Option recommendations
- Real-time updates
"""
import asyncio
import logging
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from ..services.trading_service import trading_service
from ..analyst import analyst
from ..config import settings

logger = logging.getLogger(__name__)


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat and updates.

    Client sends: {"type": "chat", "message": "AAPL"}
    Server responds: {"type": "analysis", "data": {...}}
    """
    await websocket.accept()
    logger.info("WebSocket client connected")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket message: {data}")

            message_type = data.get('type', 'chat')
            content = data.get('message', '')

            if message_type == 'chat':
                # Handle chat messages - analyze ticker if detected
                ticker = content.upper().strip()

                # Check if message looks like a ticker (1-5 uppercase letters)
                if len(ticker) <= 5 and ticker.isalpha():
                    try:
                        # Fetch stock data
                        df = await trading_service.md.get_stock_data(ticker)
                        if df is not None and not df.empty:
                            current_price = float(df['Close'].iloc[-1])

                            # Get indicators
                            indicators = {
                                'RSI': float(df['RSI'].iloc[-1]) if 'RSI' in df else None,
                                'SMA_50': float(df['SMA_50'].iloc[-1]) if 'SMA_50' in df else None,
                                'SMA_200': float(df['SMA_200'].iloc[-1]) if 'SMA_200' in df else None,
                            }

                            # Get ticker-specific news
                            news = await trading_service.md.get_news(ticker)

                            # Get market-wide news (Fed, macro, geopolitical)
                            market_news = await trading_service.md.get_market_news()

                            # Get social sentiment (contrarian signals for extreme sentiment)
                            social_sentiment = await trading_service.md.get_social_sentiment(ticker)

                            # AI analysis (run in thread pool - calls AWS Bedrock)
                            # Let the AI dynamically choose the best strategy
                            analysis = await asyncio.to_thread(
                                analyst.analyze_ticker,
                                ticker, current_price, indicators, news,
                                market_news,  # Market-wide context
                                social_sentiment  # Social sentiment with contrarian logic
                            )

                            # Get option recommendations for BUY_CALL/BUY_PUT/SELL_CALL/SELL_PUT decisions
                            option_recommendation = None
                            logger.info(f"Analysis decision: {analysis['decision']}")
                            if analysis['decision'] in ['BUY_CALL', 'BUY_PUT', 'SELL_CALL', 'SELL_PUT']:
                                logger.info(f"Finding best option for {ticker} with decision {analysis['decision']}")
                                target_premium_pct = analysis.get('target_premium_pct', 0.95)
                                # Find best option (run in thread pool - calls Robinhood API)
                                option = await asyncio.to_thread(
                                    trading_service.trader.find_best_option,
                                    ticker,
                                    analysis['decision'],
                                    settings.MAX_POSITION_SIZE,
                                    target_premium_pct
                                )

                                logger.info(f"Option returned: {option}")
                                if option:
                                    market_price = option.get('market_price', 0)
                                    limit_price = option.get('limit_price', market_price)
                                    strike = option.get('strike_price', option.get('strike', 0))
                                    # Convert strike to float if it's a string
                                    if isinstance(strike, str):
                                        strike = float(strike)
                                    expiration = option.get('expiration_date', option.get('expiration', 'N/A'))

                                    # Calculate max contracts based on budget
                                    max_contracts = int(settings.MAX_POSITION_SIZE / (market_price * 100)) if market_price > 0 else 0

                                    # Calculate exit prices based on AI recommendations
                                    exit_targets_pct = analysis.get('exit_targets', {})

                                    # Calculate actual exit prices from percentages
                                    exit_targets = None
                                    if exit_targets_pct:
                                        take_profit_pct = exit_targets_pct.get('take_profit_pct', 0.30)
                                        stop_loss_pct = exit_targets_pct.get('stop_loss_pct', 0.25)
                                        rationale = exit_targets_pct.get('rationale', 'Based on technical analysis')

                                        exit_targets = {
                                            'take_profit': {
                                                'price': round(limit_price * (1 + take_profit_pct), 2),
                                                'pct': f"+{int(take_profit_pct * 100)}%",
                                                'rationale': rationale
                                            },
                                            'stop_loss': {
                                                'price': round(limit_price * (1 - stop_loss_pct), 2),
                                                'pct': f"-{int(stop_loss_pct * 100)}%",
                                                'rationale': rationale
                                            }
                                        }

                                    option_recommendation = {
                                        "option_id": option.get('id'),
                                        "ticker": ticker,
                                        "type": analysis['decision'],
                                        "strike": strike,
                                        "expiration": expiration,
                                        "market_price": market_price,
                                        "limit_price": limit_price,
                                        "max_contracts": max_contracts,
                                        "cost_per_contract": market_price * 100,
                                        "target_premium_pct": target_premium_pct,
                                        "strategy_used": analysis.get('strategy_used', 'none'),
                                        "exit_targets": exit_targets
                                    }
                                    logger.info(f"Option recommendation created: {option_recommendation}")
                                else:
                                    logger.warning(f"No option found for {ticker} {analysis['decision']}")

                            # Send response
                            response = {
                                "type": "analysis",
                                "message": f"Analysis for {ticker}",
                                "timestamp": datetime.utcnow().isoformat(),
                                "data": {
                                    "ticker": ticker,
                                    "current_price": current_price,
                                    "decision": analysis['decision'],
                                    "confidence": analysis['confidence'],
                                    "reasoning": analysis['reasoning'],
                                    "strategy_used": analysis.get('strategy_used', 'none'),
                                    "indicators": indicators,
                                    "option_recommendation": option_recommendation
                                }
                            }
                            logger.info(f"Prepared response for {ticker}, sending to WebSocket...")
                        else:
                            response = {
                                "type": "error",
                                "message": f"Could not find data for {ticker}",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    except Exception as e:
                        logger.error(f"Error analyzing {ticker}: {e}")
                        response = {
                            "type": "error",
                            "message": f"Error analyzing {ticker}: {str(e)}",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                else:
                    # Not a ticker, send acknowledgment
                    response = {
                        "type": "info",
                        "message": "Send a ticker symbol (e.g., AAPL, TSLA) to analyze",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                try:
                    await websocket.send_json(response)
                    logger.info(f"Successfully sent response via WebSocket")
                except Exception as e:
                    logger.error(f"Error sending WebSocket response: {e}")
                    import traceback
                    traceback.print_exc()

            elif message_type == 'ping':
                # Respond to ping to keep connection alive
                await websocket.send_json({
                    "type": "pong",
                    "message": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass

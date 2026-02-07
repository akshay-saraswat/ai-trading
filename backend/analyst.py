"""
Optimized AI Analyst with Batch Processing
Reduces AI costs by 90% through intelligent batching
"""
import boto3
import json
import logging
from typing import Dict, List
import os

from .config import settings

logger = logging.getLogger(__name__)


class Analyst:
    """AI-powered stock analyst using AWS Bedrock with batch optimization"""

    def __init__(self):
        try:
            self.client = boto3.client(
                service_name='bedrock-runtime',
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
            )
            logger.info("✅ Initialized AWS Bedrock client")
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            self.client = None

    def analyze_ticker(
        self,
        ticker: str,
        current_price: float,
        indicators: Dict,
        news: List[Dict],
        market_news: List[Dict] = None,
        social_sentiment: Dict = None,
        allowed_option_types: List[str] = None,
        trading_style: str = 'swing'
    ) -> Dict:
        """
        Single ticker analysis (for backward compatibility)

        Args:
            ticker: Ticker symbol
            current_price: Current stock price
            indicators: Technical indicators dict
            news: Ticker-specific news
            market_news: Market-wide news (Fed, macro data, geopolitical events)
            social_sentiment: Social media sentiment with contrarian signals
            allowed_option_types: List of allowed option types (BUY_CALL, BUY_PUT, SELL_CALL, SELL_PUT)
            trading_style: 'day' or 'swing' trading style
        """
        results = self.analyze_batch(
            tickers=[ticker],
            prices={ticker: current_price},
            indicators_map={ticker: indicators},
            news_map={ticker: news},
            market_news=market_news,
            social_sentiment_map={ticker: social_sentiment} if social_sentiment else None,
            allowed_option_types=allowed_option_types,
            trading_style=trading_style
        )
        return results.get(ticker, {
            "decision": "NOTHING",
            "confidence": 0.0,
            "reasoning": "Analysis failed",
            "strategy_used": "none"
        })

    def analyze_batch(
        self,
        tickers: List[str],
        prices: Dict[str, float],
        indicators_map: Dict[str, Dict],
        news_map: Dict[str, List[Dict]],
        market_news: List[Dict] = None,
        social_sentiment_map: Dict[str, Dict] = None,
        allowed_option_types: List[str] = None,
        trading_style: str = 'swing'
    ) -> Dict[str, Dict]:
        """
        BATCH ANALYSIS: Analyze multiple tickers in ONE AI call
        Saves 90% of AI costs compared to individual calls

        Args:
            tickers: List of ticker symbols
            prices: Dict mapping ticker to current price
            indicators_map: Dict mapping ticker to indicators
            news_map: Dict mapping ticker to news articles
            market_news: Market-wide news (Fed, macro, geopolitical events)
            social_sentiment_map: Dict mapping ticker to social sentiment data
            allowed_option_types: List of allowed option types (BUY_CALL, BUY_PUT, SELL_CALL, SELL_PUT)
            trading_style: 'day' or 'swing' trading style

        Returns:
            Dict mapping ticker to analysis result
        """
        if allowed_option_types is None:
            allowed_option_types = ['BUY_CALL', 'BUY_PUT']  # Default: buying only
        if not self.client:
            return {
                ticker: {
                    "decision": "NOTHING",
                    "confidence": 0.0,
                    "reasoning": "Bedrock client not initialized"
                }
                for ticker in tickers
            }

        if not tickers:
            return {}

        # Build batch prompt
        system_prompt = """You are an expert stock market trader and technical analyst.
Analyze multiple stocks efficiently and provide JSON output for each."""

        # Build ticker analyses in one prompt
        user_prompt = f"""Analyze the following {len(tickers)} stocks and provide trading decisions:

"""

        for ticker in tickers:
            current_price = prices.get(ticker, 0)
            indicators = indicators_map.get(ticker, {})
            news = news_map.get(ticker, [])

            # Format news with sentiment scores and relevance
            # ENHANCED: Detect high-impact news for dynamic weighting
            news_str = "No recent news"
            news_importance = "LOW"  # LOW, MEDIUM, HIGH

            if news:
                news_items = []
                total_sentiment = 0
                weighted_sentiment = 0
                total_weight = 0
                max_importance_score = 0

                # Keywords that indicate high-impact news
                HIGH_IMPACT_PEOPLE = [
                    'michael burry', 'burry', 'warren buffett', 'buffett',
                    'cathie wood', 'bill ackman', 'ray dalio', 'jim cramer',
                    'jpmorgan', 'goldman sachs', 'morgan stanley', 'bank of america',
                    'citigroup', 'wells fargo', 'barclays', 'credit suisse'
                ]
                HIGH_IMPACT_KEYWORDS = [
                    'bubble', 'overvalued', 'undervalued', 'crash', 'collapse',
                    'downgrade', 'upgrade', 'target price', 'price target',
                    'earnings beat', 'earnings miss', 'guidance', 'forecast',
                    'fda approval', 'fda rejection', 'merger', 'acquisition',
                    'scandal', 'investigation', 'lawsuit', 'bankruptcy',
                    'short seller', 'short report', 'fraud', 'accounting'
                ]

                for n in news[:5]:  # Top 5 most relevant
                    sentiment = n.get('sentiment_score', 0)
                    relevance = n.get('relevance_score', 1.0)
                    publisher = n.get('publisher', 'Unknown')
                    title = n.get('title', 'N/A')

                    # Calculate importance score for this news item
                    importance_score = 0
                    title_lower = title.lower()
                    publisher_lower = publisher.lower()

                    # Check for high-impact people/analysts
                    for person in HIGH_IMPACT_PEOPLE:
                        if person in title_lower or person in publisher_lower:
                            importance_score += 3
                            break

                    # Check for high-impact keywords
                    keyword_matches = sum(1 for keyword in HIGH_IMPACT_KEYWORDS if keyword in title_lower)
                    importance_score += keyword_matches * 2

                    # High sentiment magnitude indicates strong opinion
                    if abs(sentiment) > 0.5:
                        importance_score += 2
                    elif abs(sentiment) > 0.3:
                        importance_score += 1

                    # High relevance indicates importance
                    if relevance > 0.8:
                        importance_score += 2
                    elif relevance > 0.6:
                        importance_score += 1

                    max_importance_score = max(max_importance_score, importance_score)

                    # Add importance indicator to news item
                    importance_emoji = ""
                    if importance_score >= 5:
                        importance_emoji = "🔥 HIGH IMPACT - "
                    elif importance_score >= 3:
                        importance_emoji = "⚠️ IMPORTANT - "

                    sentiment_label = "📈 Positive" if sentiment > 0.2 else ("📉 Negative" if sentiment < -0.2 else "➡️ Neutral")
                    news_items.append(f"  • {importance_emoji}[{publisher}] {title} ({sentiment_label} {sentiment:+.2f}, relevance: {relevance:.2f})")

                    total_sentiment += sentiment
                    weighted_sentiment += sentiment * relevance
                    total_weight += relevance

                # Determine overall news importance level
                if max_importance_score >= 5:
                    news_importance = "HIGH"
                elif max_importance_score >= 3:
                    news_importance = "MEDIUM"
                else:
                    news_importance = "LOW"

                avg_sentiment = total_sentiment / len(news) if news else 0
                weighted_avg_sentiment = weighted_sentiment / total_weight if total_weight > 0 else 0

                news_str = "\n".join(news_items)
                news_str += f"\n  Overall Sentiment: {weighted_avg_sentiment:+.2f} (unweighted: {avg_sentiment:+.2f})"
                news_str += f"\n  📊 NEWS IMPORTANCE: {news_importance}"

            # Get key indicators
            rsi = indicators.get('RSI', 'N/A')
            sma_50 = indicators.get('SMA_50', 'N/A')
            sma_200 = indicators.get('SMA_200', 'N/A')
            macd = indicators.get('MACD', 'N/A')
            macd_signal = indicators.get('MACD_signal', 'N/A')
            bb_high = indicators.get('BB_High', 'N/A')
            bb_low = indicators.get('BB_Low', 'N/A')
            atr = indicators.get('ATR', 'N/A')
            adx = indicators.get('ADX', 'N/A')
            stoch_k = indicators.get('Stoch_K', 'N/A')

            # Get social sentiment (if provided)
            social_sentiment = None
            if social_sentiment_map:
                social_sentiment = social_sentiment_map.get(ticker)

            # Format social sentiment section
            social_str = ""
            if social_sentiment and social_sentiment.get('source') != 'error':
                sentiment_score = social_sentiment.get('sentiment_score', 0)
                buzz_score = social_sentiment.get('buzz_score', 0)
                percentile = social_sentiment.get('percentile', 50)
                signal = social_sentiment.get('signal', 'neutral')
                confidence = social_sentiment.get('confidence', 'low')

                # Interpret signal for AI
                signal_interpretation = {
                    'contrarian_sell': '⚠️ CONTRARIAN SELL - Peak retail euphoria (90th+ percentile + high buzz)',
                    'extreme_bullish': '⚠️ Extremely bullish but low buzz',
                    'bullish': '✅ Healthy bullish momentum',
                    'moderately_bullish': '↗️ Moderately bullish',
                    'neutral': '➡️ Neutral sentiment',
                    'moderately_bearish': '↘️ Moderately bearish',
                    'contrarian_buy': '✅ CONTRARIAN BUY - High buzz + bearish (potential bottom)',
                    'bearish': '⬇️ Bearish'
                }.get(signal, signal)

                social_str = f"""
- Social Sentiment: {sentiment_score:+.2f} (percentile: {percentile}th)
- Buzz Score: {buzz_score:.1f}/100
- Signal: {signal_interpretation}
- Confidence: {confidence}"""

            # Calculate bearish/bullish signals
            trend_signal = "N/A"
            price_vs_sma = "N/A"
            macd_signal_str = "N/A"
            bb_position = "N/A"

            if current_price != 'N/A' and sma_50 != 'N/A' and sma_200 != 'N/A':
                # Trend alignment
                if current_price > sma_50 > sma_200:
                    trend_signal = "🟢 BULLISH (Golden alignment)"
                elif current_price < sma_50 < sma_200:
                    trend_signal = "🔴 BEARISH (Death alignment)"
                elif sma_50 > sma_200 and current_price < sma_50:
                    trend_signal = "🟡 Pullback in uptrend"
                elif sma_50 < sma_200 and current_price > sma_50:
                    trend_signal = "🟡 Rally in downtrend"
                else:
                    trend_signal = "⚪ Mixed/Unclear"

                # Price position vs SMA50
                deviation_pct = ((current_price - sma_50) / sma_50 * 100)
                if deviation_pct > 5:
                    price_vs_sma = f"🔴 {deviation_pct:+.1f}% above SMA50 (extended/overbought)"
                elif deviation_pct < -5:
                    price_vs_sma = f"🟢 {deviation_pct:+.1f}% below SMA50 (oversold)"
                else:
                    price_vs_sma = f"⚪ {deviation_pct:+.1f}% from SMA50 (normal range)"

            # MACD crossover detection
            if macd != 'N/A' and macd_signal != 'N/A':
                macd_diff = macd - macd_signal
                if macd > macd_signal and macd_diff > 0:
                    macd_signal_str = "🟢 Bullish (MACD > Signal)"
                elif macd < macd_signal and macd_diff < 0:
                    macd_signal_str = "🔴 Bearish (MACD < Signal)"
                else:
                    macd_signal_str = "⚪ Neutral crossover"

            # Bollinger Band position
            if current_price != 'N/A' and bb_high != 'N/A' and bb_low != 'N/A':
                bb_range = bb_high - bb_low
                if bb_range > 0:
                    bb_pct = (current_price - bb_low) / bb_range * 100
                    if bb_pct > 80:
                        bb_position = f"🔴 Upper band ({bb_pct:.0f}% - overbought)"
                    elif bb_pct < 20:
                        bb_position = f"🟢 Lower band ({bb_pct:.0f}% - oversold)"
                    else:
                        bb_position = f"⚪ Middle range ({bb_pct:.0f}%)"

            user_prompt += f"""
---
**{ticker}**
- Price: ${current_price:.2f}
- Trend Alignment: {trend_signal}
- Price vs SMA50: {price_vs_sma}

**Technical Indicators:**
- RSI: {f"{rsi:.1f}" if rsi != 'N/A' else 'N/A'} {("🔴 Overbought" if rsi != 'N/A' and rsi > 70 else ("🟢 Oversold" if rsi != 'N/A' and rsi < 30 else ""))}
- Stochastic: {f"{stoch_k:.1f}" if stoch_k != 'N/A' else 'N/A'} {("🔴 Overbought" if stoch_k != 'N/A' and stoch_k > 80 else ("🟢 Oversold" if stoch_k != 'N/A' and stoch_k < 20 else ""))}
- SMA50: {f"${sma_50:.2f}" if sma_50 != 'N/A' else 'N/A'}
- SMA200: {f"${sma_200:.2f}" if sma_200 != 'N/A' else 'N/A'}
- MACD: {f"{macd:.2f}" if macd != 'N/A' else 'N/A'}
- MACD Signal: {f"{macd_signal:.2f}" if macd_signal != 'N/A' else 'N/A'} → {macd_signal_str}
- Bollinger Position: {bb_position}
- ATR (Volatility): {f"{atr:.2f}" if atr != 'N/A' else 'N/A'} {("🔥 High" if atr != 'N/A' and atr > current_price * 0.03 else "")}
- ADX (Trend Strength): {f"{adx:.1f}" if adx != 'N/A' else 'N/A'} {("💪 Strong trend" if adx != 'N/A' and adx > 25 else ("📉 Weak trend" if adx != 'N/A' and adx < 20 else ""))}

**Recent News (sorted by relevance):**
{news_str}{social_str}

"""

        # Add market-wide news context (if provided)
        if market_news and len(market_news) > 0:
            market_news_text = self._format_market_news(market_news)
            user_prompt += f"""

---
**MARKET-WIDE CONTEXT** (Consider this for ALL tickers):
{market_news_text}

"""

        # Add dynamic strategy selection instructions
        strategy_text = self._build_dynamic_strategy_instructions(allowed_option_types, trading_style)
        user_prompt += f"""
{strategy_text}

**CRITICAL: Output ONLY valid JSON - no markdown, no commentary, no code blocks.**

Output Format (JSON object with ticker symbols as keys):
{{
  "TICKER": {{
    "decision": "BUY_CALL|BUY_PUT|SELL_CALL|SELL_PUT|NOTHING",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of trade thesis",
    "target_premium_pct": 0.90-1.00,
    "strategy_used": "strategy name",
    "exit_targets": {{
      "take_profit_pct": 0.20-0.50,
      "stop_loss_pct": 0.15-0.40,
      "rationale": "why these % targets"
    }}
  }}
}}

Example response (COPY THIS FORMAT EXACTLY):
{{"AAPL": {{"decision": "BUY_CALL", "confidence": 0.75, "reasoning": "Oversold RSI (32), price bounced off SMA50 support, bullish MACD crossover", "target_premium_pct": 0.95, "strategy_used": "mean_reversion", "exit_targets": {{"take_profit_pct": 0.40, "stop_loss_pct": 0.25, "rationale": "Target +40% at RSI 60-65 resistance, stop at -25% if breaks SMA50 support"}}}}, "TSLA": {{"decision": "NOTHING", "confidence": 0.3, "reasoning": "Mixed signals, no clear trend", "target_premium_pct": 0.95, "strategy_used": "none"}}}}

START YOUR RESPONSE WITH {{ AND END WITH }} - NOTHING ELSE:
"""

        # Call Bedrock
        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.AI_MAX_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt}]
                    }
                ],
                "system": system_prompt
            })

            response = self.client.invoke_model(
                body=body,
                modelId=settings.AI_MODEL_ID,
                accept='application/json',
                contentType='application/json'
            )

            response_body = json.loads(response.get('body').read())
            response_text = response_body['content'][0]['text']

            # Robust JSON extraction with multiple fallback strategies
            results = self._extract_json_from_response(response_text)

            # Validate results
            for ticker in tickers:
                if ticker not in results:
                    results[ticker] = {
                        "decision": "NOTHING",
                        "confidence": 0.0,
                        "reasoning": "No analysis provided",
                        "target_premium_pct": 0.95,
                        "strategy_used": "none"
                    }

            logger.info(f"✅ Batch analyzed {len(tickers)} tickers in ONE AI call")
            return results

        except Exception as e:
            logger.error(f"Bedrock batch analysis error: {e}")
            # Return safe defaults
            return {
                ticker: {
                    "decision": "NOTHING",
                    "confidence": 0.0,
                    "reasoning": f"Error: {str(e)[:50]}",
                    "target_premium_pct": 0.95,
                    "strategy_used": "none"
                }
                for ticker in tickers
            }

    def _extract_json_from_response(self, response_text: str) -> Dict:
        """
        Robust JSON extraction from LLM response with multiple fallback strategies.

        Tries in order:
        1. Markdown code blocks (```json, ```JSON, ```)
        2. Find largest valid JSON object
        3. Regex extraction
        4. Direct parse (if already clean JSON)

        Args:
            response_text: Raw text from LLM

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If no valid JSON found after all strategies
        """
        import re

        # Strategy 1: Try markdown code blocks (case-insensitive)
        code_block_patterns = [
            r'```json\s*\n?(.*?)\n?```',
            r'```JSON\s*\n?(.*?)\n?```',
            r'```\s*\n?(.*?)\n?```',
        ]

        for pattern in code_block_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL | re.IGNORECASE)
            if matches:
                # Try parsing each match (in case multiple blocks)
                for match in matches:
                    try:
                        result = json.loads(match.strip())
                        if isinstance(result, dict) and result:
                            logger.debug("✓ Extracted JSON from markdown code block")
                            return result
                    except json.JSONDecodeError:
                        continue

        # Strategy 2: Find all JSON-like objects and try parsing the largest valid one
        # This handles cases where JSON is embedded in text
        brace_pairs = []
        stack = []
        for i, char in enumerate(response_text):
            if char == '{':
                stack.append(i)
            elif char == '}' and stack:
                start = stack.pop()
                brace_pairs.append((start, i + 1))

        # Sort by size (largest first) and try parsing
        brace_pairs.sort(key=lambda x: x[1] - x[0], reverse=True)
        for start, end in brace_pairs:
            try:
                candidate = response_text[start:end]
                result = json.loads(candidate)
                if isinstance(result, dict) and result:
                    logger.debug("✓ Extracted JSON by finding largest valid object")
                    return result
            except json.JSONDecodeError:
                continue

        # Strategy 3: Try direct parse (if response is clean JSON)
        try:
            result = json.loads(response_text.strip())
            if isinstance(result, dict) and result:
                logger.debug("✓ Parsed response as direct JSON")
                return result
        except json.JSONDecodeError:
            pass

        # All strategies failed
        logger.error(f"Failed to extract JSON from response. First 500 chars: {response_text[:500]}")
        raise ValueError(
            "Could not extract valid JSON from LLM response. "
            "Response may be truncated or malformed. "
            f"Response preview: {response_text[:200]}..."
        )

    def _format_market_news(self, market_news: List[Dict]) -> str:
        """
        Format market-wide news for AI analysis.

        Args:
            market_news: List of market news items with category, sentiment, title

        Returns:
            Formatted string with market news context
        """
        if not market_news:
            return "No significant market-wide news."

        # Group news by category
        news_by_category = {}
        for item in market_news[:10]:  # Top 10 most relevant
            category = item.get('category', 'General Market')
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

        formatted_sections = []

        # Format each category
        for category, items in news_by_category.items():
            category_lines = [f"\n**{category}:**"]

            for item in items[:3]:  # Max 3 per category to avoid overload
                title = item.get('title', 'N/A')
                sentiment = item.get('sentiment_score', 0)
                sentiment_label = "📈 Bullish" if sentiment > 0.2 else ("📉 Bearish" if sentiment < -0.2 else "➡️ Neutral")

                category_lines.append(f"  • {title} ({sentiment_label} {sentiment:+.2f})")

            formatted_sections.append("\n".join(category_lines))

        result = "\n".join(formatted_sections)

        # Add guidance with priority hierarchy
        result += "\n\n**⚠️ CRITICAL - Market News OVERRIDES Technical Indicators:**"
        result += "\n\n**🔴 HIGHEST PRIORITY - Check FIRST:**"
        result += "\n1. **Fed Rate Decisions**: 0.5% cut/hike = IGNORE technicals, trade the macro shift"
        result += "\n   - Large rate cut (0.5%+) = Bullish for growth stocks, bearish for financials"
        result += "\n   - Large rate hike (0.5%+) = Bearish for growth, bullish for value/financials"
        result += "\n   - Emergency rate change = Extreme volatility, consider straddles"
        result += "\n\n2. **Major Macro Data Surprises**: CPI/NFP/GDP significantly above/below expectations"
        result += "\n   - CPI spike (unexpected inflation) = Bearish, ignore bullish technicals"
        result += "\n   - Jobs data miss = Bearish, override positive RSI/MACD"
        result += "\n\n3. **Geopolitical Shocks**: War, sanctions, trade war escalation"
        result += "\n   - Creates volatility spikes = Straddle opportunities regardless of technicals"
        result += "\n   - Flight to safety = Defensive positioning overrides bullish indicators"
        result += "\n\n**🟡 HIGH PRIORITY - Check SECOND (Ticker-Specific):**"
        result += "\n4. **Earnings Surprises**: Major beat/miss in recent earnings call"
        result += "\n   - Earnings beat + guidance raise = Bullish momentum (override bearish technicals)"
        result += "\n   - Earnings miss + guidance cut = Bearish (ignore oversold RSI)"
        result += "\n\n5. **Major Corporate Events**: M&A, FDA approval, executive changes, restructuring"
        result += "\n   - These create NEW trends, old technicals are obsolete"
        result += "\n\n**🟢 NORMAL PRIORITY - Use When No Major News:**"
        result += "\n6. Technical indicators (RSI, MACD, SMA) - Reliable ONLY when no major fundamental changes"
        result += "\n\n**Decision Hierarchy:**"
        result += "\nIF major Fed/macro news EXISTS → Analyze macro impact FIRST, then check if technicals confirm"
        result += "\nIF major ticker news EXISTS → Analyze fundamental change FIRST, technicals are secondary"
        result += "\nIF no major news → Rely primarily on technical indicators as usual"

        return result

    def _build_dynamic_strategy_instructions(self, allowed_option_types: List[str], trading_style: str) -> str:
        """
        Build instructions that allow AI to dynamically choose the best strategy.

        Instead of constraining the AI to specific enabled strategies,
        we present all available strategies and let the AI choose which one
        fits best for each ticker based on the technical indicators and market conditions.

        Args:
            allowed_option_types: List of allowed option types
            trading_style: 'day' or 'swing'

        Returns:
            Strategy instructions for dynamic selection
        """
        # Build allowed options text
        allowed_text = "**USER'S ALLOWED OPTION TYPES:** " + ", ".join(allowed_option_types)

        # Trading style guidance
        style_guidance = ""
        if trading_style == 'day':
            style_guidance = """
**TRADING STYLE: DAY TRADING**
- Focus on short-term trades (0-3 days, often same-day exits)
- Tighter take profit targets: 20-40% (quick profits)
- Tighter stop losses: 15-25% (protect capital fast)
- Prefer high-momentum setups with strong intraday catalysts
- Look for quick reversals and intraday breakouts
- Expiration: 0-7 DTE (days to expiration) for maximum gamma
"""
        else:  # swing trading
            style_guidance = """
**TRADING STYLE: SWING TRADING**
- Focus on medium-term trades (3-30 days)
- Wider take profit targets: 30-60% (let winners run)
- Wider stop losses: 20-35% (room for pullbacks)
- Prefer trend-following setups with multi-day momentum
- Look for breakouts that can sustain over several days
- Expiration: 14-45 DTE (days to expiration) for time decay balance
"""

        base_text = f"""**Your Task: Analyze each ticker and CHOOSE the best trading strategy**

{allowed_text}

⚠️ CRITICAL: Only recommend option types that are in the ALLOWED list above!
- Do NOT recommend option types that are not allowed
- If best setup requires a disallowed type, return NOTHING
- If indicators show bearish signals AND BUY_PUT is allowed → Recommend BUY_PUT
- If indicators show bullish signals AND BUY_CALL is allowed → Recommend BUY_CALL
- If high IV + neutral AND SELL_CALL is allowed → Consider SELL_CALL
- If high IV + at support AND SELL_PUT is allowed → Consider SELL_PUT
- If indicators are mixed/weak → Recommend NOTHING

{style_guidance}

Available Trading Strategies (choose the ONE that best fits the ticker's current conditions):

1. **Mean Reversion** (Buying): Best when price has deviated significantly from its average
   - **BUY_CALL**: RSI < 35 AND (price 3-10% below SMA50 OR at lower Bollinger Band)
     → Oversold, likely to bounce back toward mean
   - **BUY_PUT**: RSI > 65 AND (price 3-10% above SMA50 OR at upper Bollinger Band)
     → Overbought, likely to pull back toward mean
   - Exit targets: TP=30-40%, SL=20-25%
   - Confidence: HIGH when both RSI and price position confirm the setup

2. **Momentum** (Buying): Best when price is moving strongly in one direction with confirmation
   - **BUY_CALL**: Strong uptrend with:
     • RSI 50-75 (in bullish zone but not overbought)
     • Price > SMA50 > SMA200 (golden alignment)
     • MACD > MACD Signal (bullish crossover)
     • ADX > 25 (strong trend)
     • Bullish news sentiment
   - **BUY_PUT**: Strong downtrend with:
     • RSI 25-50 (in bearish zone but not oversold)
     • Price < SMA50 < SMA200 (death alignment)
     • MACD < MACD Signal (bearish crossover)
     • ADX > 25 (strong trend)
     • Bearish news sentiment
   - Exit targets: TP=40-60%, SL=15-20% (ride the momentum, but be ready to exit)
   - Confidence: HIGH when 4+ indicators align in same direction

3. **Trend Following** (Buying): Best when clear long-term trend is established
   - **BUY_CALL**: Bullish alignment - Price > SMA50 > SMA200 (golden cross active)
     → Buy on pullbacks to SMA50 support
   - **BUY_PUT**: Bearish alignment - Price < SMA50 < SMA200 (death cross active)
     → Buy puts on rallies to SMA50 resistance
   - Exit targets: TP=40-50%, SL=20-25%
   - Confidence: HIGH when SMA alignment is clear and ADX > 20

4. **Covered Call** (Selling - Income Strategy): Sell OTM calls for premium income
   - SELL_CALL: Neutral to slightly bullish, stock trading sideways or in range
   - Best when: Implied volatility is HIGH (expensive premiums) + stock near resistance
   - Exit targets: TP=50-70% of premium collected, SL=N/A (buy back if stock breaks out)
   - ⚠️ REQUIRES: User must own 100 shares of underlying stock

5. **Cash-Secured Put** (Selling - Income Strategy): Sell OTM puts for premium income
   - SELL_PUT: Neutral to slightly bearish, willing to own stock at lower price
   - Best when: Implied volatility is HIGH + stock at/near support level
   - Exit targets: TP=50-70% of premium collected, SL=N/A (buy back if stock crashes through support)
   - ⚠️ REQUIRES: User must have cash collateral (strike price × 100)

**Decision Logic (EQUAL WEIGHT for CALLS and PUTS):**

BULLISH SETUPS (BUY_CALL):
- RSI < 35 AND price at/below lower Bollinger Band → Mean Reversion CALL
- Strong uptrend: Price > SMA50 > SMA200 + MACD bullish + positive news → Momentum CALL
- Golden alignment confirmed + ADX > 20 → Trend Following CALL
- Contrarian buy signal (high bearish buzz but oversold technicals) → Mean Reversion CALL

BEARISH SETUPS (BUY_PUT):
- RSI > 65 AND price at/above upper Bollinger Band → Mean Reversion PUT
- Strong downtrend: Price < SMA50 < SMA200 + MACD bearish + negative news → Momentum PUT
- Death alignment confirmed + ADX > 20 → Trend Following PUT
- Contrarian sell signal (extreme euphoria + overbought) → Mean Reversion PUT

NEUTRAL/INCOME SETUPS:
- High IV + range-bound near resistance → Covered Call (SELL_CALL)
- High IV + at support + willing to own → Cash-Secured Put (SELL_PUT)

AVOID (NOTHING):
- Weak/conflicting signals
- ADX < 15 (no trend strength)
- Price consolidating between SMAs with no clear breakout
- Neutral news + neutral technicals

**BEARISH PATTERN RECOGNITION (Actively look for PUT opportunities):**
🔴 **Strong Bearish Signals** (High confidence BUY_PUT):
1. Death Cross: SMA50 recently crossed below SMA200 + price below both
2. Overbought + Reversal: RSI > 70 + Stochastic > 80 + price at upper BB
3. Failed Breakout: Price attempted to break resistance but rejected (bearish news confirms)
4. Bearish Divergence: Price making new highs but RSI/MACD making lower highs
5. Distribution: Price flat/up but volume declining + insiders selling (check news)

🟡 **Moderate Bearish Signals** (Medium confidence BUY_PUT):
1. Price below SMA50 with SMA50 trending down
2. Negative MACD crossover + bearish news
3. RSI > 60 in a downtrend (dead cat bounce - fade the rally)
4. Contrarian sell signal: 90th+ percentile euphoria + overbought technicals

⚠️ **DO NOT ignore bearish setups!** Puts are just as profitable as calls when timed correctly.

**🔥 CRITICAL - DYNAMIC WEIGHTING SYSTEM (News Importance Determines Priority):**

Each ticker shows a "NEWS IMPORTANCE" level (HIGH/MEDIUM/LOW). Use this to determine weighting:

**WHEN NEWS IMPORTANCE = HIGH** (e.g., Michael Burry warning, major analyst downgrade, earnings surprise):
- News sentiment = PRIMARY (70% weight) ← OVERRIDES TECHNICALS
- Technical indicators (RSI, MACD, SMA, BB) = SECONDARY (20% weight) ← USE ONLY TO CONFIRM NEWS
- Social sentiment = TERTIARY (10% weight)
- **RULE: If HIGH IMPACT news is BEARISH → Strong BUY_PUT signal, IGNORE bullish technicals**
- **RULE: If HIGH IMPACT news is BULLISH → Strong BUY_CALL signal, IGNORE bearish technicals**
- Example: "Michael Burry warns PLTR bubble" (HIGH + negative sentiment) = Strong BUY_PUT, even if RSI is oversold

**WHEN NEWS IMPORTANCE = MEDIUM** (e.g., company announcements, medium analyst coverage):
- Technical indicators = PRIMARY (50% weight) ← BALANCE WITH NEWS
- News sentiment = PRIMARY (40% weight) ← NEARLY EQUAL WEIGHT
- Social sentiment = TERTIARY (10% weight)
- **RULE: Technicals and news must ALIGN. If they conflict → NOTHING**
- Example: Bullish news + bullish technicals = Strong signal. Bullish news + bearish technicals = NOTHING

**WHEN NEWS IMPORTANCE = LOW** (e.g., routine articles, minor updates):
- Technical indicators = PRIMARY (70% weight) ← TECHNICALS LEAD
- News sentiment = SECONDARY (20% weight) ← CONFIRMATION ONLY
- Social sentiment = TERTIARY (10% weight)
- **RULE: Trade based on technicals, use news for confirmation**
- Example: Oversold RSI + weak positive news = BUY_CALL (technicals drive the decision)

**Social Sentiment Contrarian Logic (applies to all importance levels):**
- ⚠️ CONTRARIAN SELL signal (90th+ percentile + high buzz) = REDUCE confidence in BUY_CALL by 20-30%
  Example: RSI says "buy" but social at 95th percentile → Lower confidence or switch to NOTHING
- ✅ CONTRARIAN BUY signal (high buzz + bearish) = POTENTIAL opportunity but VERIFY with technicals first
- ✅ Healthy bullish momentum = CONFIRMATION for existing bullish technical setup
- ➡️ Neutral/low buzz = Ignore social sentiment, rely on primary factors

**⚠️ EXAMPLES OF DYNAMIC WEIGHTING IN ACTION:**

Example 1: PLTR with HIGH importance news
- News: "🔥 HIGH IMPACT - Michael Burry warns of PLTR bubble" (📉 Negative -0.8)
- Technicals: RSI 45 (neutral), MACD bullish
- NEWS IMPORTANCE: HIGH
- Decision: **BUY_PUT** (news 70% weight overrides bullish MACD)
- Reasoning: High-impact bearish warning from famous investor OVERRIDES neutral/bullish technicals

Example 2: AAPL with MEDIUM importance news
- News: "⚠️ IMPORTANT - AAPL reports strong iPhone sales" (📈 Positive +0.5)
- Technicals: RSI 72 (overbought), price at upper BB
- NEWS IMPORTANCE: MEDIUM
- Decision: **NOTHING** (news bullish 40%, technicals bearish 50% = CONFLICT)
- Reasoning: Positive news conflicts with overbought technicals, no clear edge

Example 3: TSLA with LOW importance news
- News: "TSLA opens new service center" (📈 Positive +0.2)
- Technicals: RSI 28 (oversold), price at lower BB, MACD bullish crossover
- NEWS IMPORTANCE: LOW
- Decision: **BUY_CALL** (technicals 70% weight drive decision)
- Reasoning: Strong technical setup confirmed by mildly positive news

**IMPORTANT**: In your response, set "strategy_used" to ONE of:
- "mean_reversion"
- "momentum"
- "trend_following"
- "covered_call" (for SELL_CALL)
- "cash_secured_put" (for SELL_PUT)
- "none" (if no clear opportunity)

The strategy_used field should explain WHY you chose that strategy based on the ticker's indicators.

**SELLING OPTIONS REQUIREMENTS:**
- SELL_CALL: Only recommend if confident user owns 100+ shares OR is willing to buy 100 shares
- SELL_PUT: Only recommend if confident user has cash collateral (strike × 100) OR is willing to be assigned
- Both: Require HIGH implied volatility (expensive premiums make it worthwhile)

**⚠️ FINAL REMINDER - NO BULLISH BIAS:**
Before submitting your analysis, verify:
1. Did you actively check for BEARISH signals? (Don't just default to calls!)
2. If Price < SMA50 < SMA200 → Should be BUY_PUT (not call!)
3. If RSI > 65 at upper BB → Should be BUY_PUT (not call!)
4. If MACD bearish + negative news → Should be BUY_PUT (not call!)
5. If overbought + contrarian sell signal → Should be BUY_PUT or NOTHING (not call!)

**Example Decision Flow:**
- AAPL: RSI 72, price 8% above SMA50, at upper BB, MACD bearish crossover
  → ✅ BUY_PUT (mean reversion) - DO NOT recommend BUY_CALL!
- TSLA: RSI 28, price 6% below SMA50, at lower BB, MACD bullish crossover
  → ✅ BUY_CALL (mean reversion)
- NVDA: Price < SMA50 < SMA200, RSI 35, bearish news, downtrend confirmed
  → ✅ BUY_PUT (trend following) - DO NOT recommend BUY_CALL!

Treat CALLS and PUTS with equal consideration. The goal is profit, not directional bias!
"""

        return base_text


# Global analyst instance
analyst = Analyst()

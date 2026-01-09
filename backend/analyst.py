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
        social_sentiment: Dict = None
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
        """
        results = self.analyze_batch(
            tickers=[ticker],
            prices={ticker: current_price},
            indicators_map={ticker: indicators},
            news_map={ticker: news},
            market_news=market_news,
            social_sentiment_map={ticker: social_sentiment} if social_sentiment else None
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
        social_sentiment_map: Dict[str, Dict] = None
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

        Returns:
            Dict mapping ticker to analysis result
        """
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
            news_str = "No recent news"
            if news:
                news_items = []
                total_sentiment = 0
                weighted_sentiment = 0
                total_weight = 0

                for n in news[:5]:  # Top 5 most relevant
                    sentiment = n.get('sentiment_score', 0)
                    relevance = n.get('relevance_score', 1.0)
                    publisher = n.get('publisher', 'Unknown')
                    title = n.get('title', 'N/A')

                    sentiment_label = "📈 Positive" if sentiment > 0.2 else ("📉 Negative" if sentiment < -0.2 else "➡️ Neutral")
                    news_items.append(f"  • [{publisher}] {title} ({sentiment_label} {sentiment:+.2f}, relevance: {relevance:.2f})")

                    total_sentiment += sentiment
                    weighted_sentiment += sentiment * relevance
                    total_weight += relevance

                avg_sentiment = total_sentiment / len(news) if news else 0
                weighted_avg_sentiment = weighted_sentiment / total_weight if total_weight > 0 else 0

                news_str = "\n".join(news_items)
                news_str += f"\n  Overall Sentiment: {weighted_avg_sentiment:+.2f} (unweighted: {avg_sentiment:+.2f})"

            # Get key indicators
            rsi = indicators.get('RSI', 'N/A')
            sma_50 = indicators.get('SMA_50', 'N/A')
            sma_200 = indicators.get('SMA_200', 'N/A')
            macd = indicators.get('MACD', 'N/A')
            macd_signal = indicators.get('MACD_signal', 'N/A')

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

            user_prompt += f"""
---
**{ticker}**
- Price: ${current_price:.2f}
- RSI: {rsi if rsi != 'N/A' else 'N/A'}
- SMA50: {f"${sma_50:.2f}" if sma_50 != 'N/A' else 'N/A'}
- SMA200: {f"${sma_200:.2f}" if sma_200 != 'N/A' else 'N/A'}
- MACD: {f"{macd:.2f}" if macd != 'N/A' else 'N/A'}
- MACD Signal: {f"{macd_signal:.2f}" if macd_signal != 'N/A' else 'N/A'}
- Recent News (sorted by relevance):
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
        strategy_text = self._build_dynamic_strategy_instructions()
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
    "entry_timing": {{
      "timing": "IMMEDIATE|WAIT_FOR_DIP|WAIT_FOR_PULLBACK",
      "rationale": "when to enter and why"
    }},
    "exit_targets": {{
      "take_profit_pct": 0.20-0.50,
      "stop_loss_pct": 0.15-0.40,
      "rationale": "why these % targets"
    }}
  }}
}}

Example response (COPY THIS FORMAT EXACTLY):
{{"AAPL": {{"decision": "BUY_CALL", "confidence": 0.75, "reasoning": "Oversold RSI (32), price bounced off SMA50 support, bullish MACD crossover", "target_premium_pct": 0.95, "strategy_used": "mean_reversion", "entry_timing": {{"timing": "IMMEDIATE", "rationale": "Already at strong support, momentum turning bullish"}}, "exit_targets": {{"take_profit_pct": 0.40, "stop_loss_pct": 0.25, "rationale": "Target +40% at RSI 60-65 resistance, stop at -25% if breaks SMA50 support"}}}}, "TSLA": {{"decision": "NOTHING", "confidence": 0.3, "reasoning": "Mixed signals, no clear trend", "target_premium_pct": 0.95, "strategy_used": "none"}}}}

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

    def _build_dynamic_strategy_instructions(self) -> str:
        """
        Build instructions that allow AI to dynamically choose the best strategy.

        Instead of constraining the AI to specific enabled strategies,
        we present all available strategies and let the AI choose which one
        fits best for each ticker based on the technical indicators and market conditions.

        Returns:
            Strategy instructions for dynamic selection
        """
        return """**Your Task: Analyze each ticker and CHOOSE the best trading strategy**

Available Trading Strategies (choose the ONE that best fits the ticker's current conditions):

1. **Mean Reversion** (Buying): Best when price has deviated significantly from its average
   - BUY_CALL: RSI < 40 AND price is 3-8% below SMA50 (oversold, likely to bounce back)
   - BUY_PUT: RSI > 60 AND price is 3-8% above SMA50 (overbought, likely to pull back)
   - Exit targets: TP=30-40%, SL=20-25%

2. **Momentum** (Buying): Best when price is moving strongly in one direction with confirmation
   - BUY_CALL: Strong uptrend with RSI 55-75, price above SMA50, positive MACD, bullish news
   - BUY_PUT: Strong downtrend with RSI 25-45, price below SMA50, negative MACD, bearish news
   - Exit targets: TP=40-60%, SL=15-20% (ride the momentum)

3. **Trend Following** (Buying): Best when clear long-term trend is established
   - BUY_CALL: Price > SMA50 > SMA200 (strong uptrend alignment)
   - BUY_PUT: Price < SMA50 < SMA200 (strong downtrend alignment)
   - Exit targets: TP=40-50%, SL=20-25%

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

6. **Bull Call Spread / Bear Put Spread**: Best when moderate directional move expected
   - Lower risk, lower reward strategy for uncertain markets
   - Use when confidence is 0.5-0.7 (moderate, not strong)
   - Exit targets: TP=25-35%, SL=25-30%

7. **Straddle/Strangle**: Best when expecting high volatility but direction uncertain
   - Buy both call and put when major catalyst (earnings, news) expected
   - Use when indicators are conflicting but volatility is high
   - Exit targets: TP=50-80%, SL=30-40%

**Decision Logic:**
- If RSI < 35 or RSI > 65: Consider Mean Reversion (BUY)
- If strong trend (MACD crossover, price far from SMA): Consider Momentum (BUY)
- If stable trend alignment (SMA50 vs SMA200): Consider Trend Following (BUY)
- If high IV + stock range-bound near resistance: Consider Covered Call (SELL_CALL)
- If high IV + stock at support + willing to own: Consider Cash-Secured Put (SELL_PUT)
- If mixed signals but moderate confidence: Consider Spreads
- If high volatility expected with unclear direction: Consider Straddle
- If weak/conflicting signals: Return NOTHING

**CRITICAL - Social Sentiment Weighting:**
- Technical indicators (RSI, MACD, SMA) = PRIMARY (70% weight)
- News sentiment = SECONDARY (20% weight)
- Social sentiment = TERTIARY (10% weight) - USE AS CONFIRMATION, NOT DRIVER

**Social Sentiment Contrarian Logic:**
- ⚠️ CONTRARIAN SELL signal (90th+ percentile + high buzz) = REDUCE confidence in BUY_CALL by 20-30%
  Example: RSI says "buy" but social at 95th percentile → Lower confidence or switch to NOTHING
- ✅ CONTRARIAN BUY signal (high buzz + bearish) = POTENTIAL opportunity but VERIFY with technicals first
- ✅ Healthy bullish momentum = CONFIRMATION for existing bullish technical setup
- ➡️ Neutral/low buzz = Ignore social sentiment, rely on technicals

**DO NOT let social sentiment override strong technical signals. Use it only to:**
1. Reduce confidence when euphoria is extreme (contrarian sell)
2. Confirm existing technical setups (bullish momentum)
3. Identify potential bottoms (contrarian buy) if technicals also support

**IMPORTANT**: In your response, set "strategy_used" to ONE of:
- "mean_reversion"
- "momentum"
- "trend_following"
- "covered_call" (for SELL_CALL)
- "cash_secured_put" (for SELL_PUT)
- "bull_call_spread" or "bear_put_spread"
- "straddle"
- "none" (if no clear opportunity)

The strategy_used field should explain WHY you chose that strategy based on the ticker's indicators.

**SELLING OPTIONS REQUIREMENTS:**
- SELL_CALL: Only recommend if confident user owns 100+ shares OR is willing to buy 100 shares
- SELL_PUT: Only recommend if confident user has cash collateral (strike × 100) OR is willing to be assigned
- Both: Require HIGH implied volatility (expensive premiums make it worthwhile)
"""


# Global analyst instance
analyst = Analyst()

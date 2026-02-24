import robin_stocks.robinhood as r
import math
import datetime
import time
import logging

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self):
        self.logged_in = False

    def is_logged_in(self):
        """
        Check if there's an active Robinhood session.
        Returns True if logged in, False otherwise.
        """
        try:
            # Try to load account profile to verify session is active
            profile = r.profiles.load_account_profile()
            return profile is not None and isinstance(profile, dict)
        except Exception:
            return False

    @staticmethod
    def round_option_price(price):
        """
        Rounds option price according to Robinhood rules:
        - Prices >= $1.00: Round to nearest $0.05
        - Prices < $1.00: Round to nearest $0.01
        """
        if price >= 1.00:
            # Round to nearest $0.05
            return round(price * 20) / 20
        else:
            # Round to nearest $0.01
            return round(price, 2)

    def get_all_open_option_positions(self):
        """
        Fetches all open option positions from Robinhood account.
        Returns a list of position dictionaries with details.
        """
        if not self.is_logged_in():
            logger.warning("Not logged in - returning empty positions list")
            return []

        try:
            logger.debug("Fetching open option positions from Robinhood...")

            # Get all option positions
            positions = r.get_open_option_positions()

            if not positions:
                logger.info("No open option positions found")
                return []

            result = []

            for pos in positions:
                try:
                    # Extract position details
                    quantity = float(pos.get('quantity', 0))

                    # Skip if quantity is 0 or position is closed
                    if quantity == 0:
                        continue

                    # Get average price per contract
                    price_per_contract = float(pos.get('average_price', 0))

                    # Get option instrument URL and ID
                    option_url = pos.get('option')
                    if not option_url:
                        continue

                    # Extract option ID from URL
                    option_id = option_url.split('/')[-2] if option_url else None

                    if not option_id:
                        continue

                    # Get option instrument details
                    instrument = r.get_option_instrument_data_by_id(option_id)

                    if not instrument:
                        continue

                    # Extract details
                    ticker = instrument.get('chain_symbol')
                    strike = float(instrument.get('strike_price', 0))
                    expiration = instrument.get('expiration_date')
                    option_type = instrument.get('type')  # 'call' or 'put'

                    # Get current market data
                    market_data = r.get_option_market_data_by_id(option_id)
                    if isinstance(market_data, list) and len(market_data) > 0:
                        market_data = market_data[0]

                    # Current price per contract from market
                    current_price_per_contract = float(market_data.get('adjusted_mark_price', 0)) if market_data else 0

                    # Calculate total entry cost and current value
                    # Entry: price_per_contract * number_of_contracts
                    # Current: current_price_per_contract * number_of_contracts
                    entry_price = price_per_contract * quantity
                    current_price = current_price_per_contract * quantity * 100  # Each contract represents 100 shares

                    # Calculate P&L
                    if current_price > 0 and entry_price > 0:
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100
                        pnl_dollars = current_price - entry_price
                    else:
                        pnl_percent = 0
                        pnl_dollars = 0

                    # Determine decision type
                    decision = 'BUY_CALL' if option_type == 'call' else 'BUY_PUT'

                    # Build position object
                    position_data = {
                        'ticker': ticker,
                        'decision': decision,
                        'entry_price': entry_price,
                        'current_price': current_price,
                        'strike': strike,
                        'expiration': expiration,
                        'contracts': int(quantity),
                        'option_id': option_id,
                        'pnl_percent': pnl_percent,
                        'pnl_dollars': pnl_dollars,
                        'option_type': option_type,
                        'source': 'robinhood'  # Mark as coming from Robinhood
                    }

                    result.append(position_data)
                    logger.debug(f"Found position: {ticker} {strike} {option_type} - {quantity} contracts, Entry: ${entry_price:.2f}, Current: ${current_price:.2f} ({pnl_percent:+.2f}%)")

                except Exception as e:
                    logger.error(f"Error processing position: {e}")
                    continue

            logger.info(f"📊 Total open positions: {len(result)}")
            return result

        except Exception as e:
            logger.error(f"Error fetching option positions: {e}")
            import traceback
            logger.exception("Full traceback:")
            return []

    def find_best_option(self, ticker, decision, budget=1000, target_premium_pct=1.0):
        """
        Finds a suitable option contract.
        decision: "BUY_CALL", "BUY_PUT", "SELL_CALL", or "SELL_PUT"
        target_premium_pct: Percentage of market price to use as limit order (0.90-1.00)

        For selling options:
        - SELL_CALL: Covered call (requires owning 100 shares) or naked (high risk)
        - SELL_PUT: Cash-secured put (requires cash collateral) or naked (high risk)

        Returns None if unable to fetch option data.
        """
        try:
            # Get current price
            current_price = float(r.get_latest_price(ticker)[0])
            logger.debug(f"Current price of {ticker}: ${current_price:.2f}")

            # Determine option type (call or put) - works for both buying and selling
            option_type = "call" if decision in ["BUY_CALL", "SELL_CALL"] else "put"

            # Get expirations
            chains = r.get_chains(ticker)
            logger.debug(f"Chains data: {chains}")

            if not chains or 'expiration_dates' not in chains:
                logger.error(f"No option chains found for {ticker}")
                return None

            expirations = chains['expiration_dates']

            if not expirations:
                logger.error(f"No expiration dates found for {ticker}")
                return None

            logger.debug(f"Available expirations: {expirations}")

            # Sort and pick one ~1 week out
            valid_dates = [d for d in expirations if d > (datetime.date.today() + datetime.timedelta(days=7)).isoformat()]
            if not valid_dates:
                target_date = expirations[-1] # Fallback
            else:
                target_date = valid_dates[0]

            logger.debug(f"Targeting expiration: {target_date}")

            options = r.find_options_by_expiration(ticker, target_date, optionType=option_type)

            if not options:
                logger.error(f"No {option_type} options found for {ticker} expiring {target_date}")
                return None

            logger.debug(f"Found {len(options)} {option_type} options")

            # Filter for strike near price
            # Sort by distance from current price
            options.sort(key=lambda x: abs(float(x['strike_price']) - current_price))

            # Select the closest one (ATM)
            best_option = options[0]
            logger.debug(f"📊 Selected option: Strike ${best_option['strike_price']} (closest to ${current_price:.2f})")

            # Get market data for this option to check liqudity/price
            market_data = r.get_option_market_data_by_id(best_option['id'])
            if isinstance(market_data, list):
                market_data = market_data[0]

            ask_price = float(market_data['adjusted_mark_price']) # or ask_price

            # Calculate limit price based on mean reversion strategy
            limit_price_raw = ask_price * target_premium_pct

            # Round according to Robinhood rules to avoid subpenny increment errors
            limit_price = self.round_option_price(limit_price_raw)

            logger.debug(f"💰 Market: ${ask_price:.2f}, Limit: ${limit_price:.2f} ({target_premium_pct*100:.0f}% of market)")
            if limit_price != limit_price_raw:
                logger.debug(f"  Note: Rounded from ${limit_price_raw:.4f} to comply with Robinhood pricing rules")

            best_option['market_price'] = ask_price
            best_option['limit_price'] = limit_price
            best_option['expiration'] = best_option.get('expiration_date') or target_date
            return best_option

        except Exception as e:
            logger.error(f"Error finding options: {e}")
            import traceback
            logger.exception("Full traceback:")
            return None

    def place_trade(self, option, budget=1000):
        """
        Places the buy order using limit price for mean reversion strategy.
        """
        # Use limit_price for placing order (below market for better entry)
        limit_price = option.get('limit_price', option.get('market_price', 5.00))
        market_price = option.get('market_price', 5.00)

        # Calculate contracts based on market price (to know how many we can afford)
        # but place order at limit price
        contracts = math.floor(budget / (market_price * 100))

        if contracts < 1:
            logger.warning(f"⚠️  Budget ${budget} too low for option price ${market_price} (x100 = ${market_price*100})")
            return None

        logger.info(f"🛒 Preparing to buy {contracts} contracts of {option['symbol']} {option['expiration']} {option['type']} ${option.get('strike_price', 150)}")
        logger.info(f"  Market: ${market_price:.2f}, Limit: ${limit_price:.2f}")

        if not self.is_logged_in():
            logger.info("🎮 Simulation: Trade executed")
            return {"id": "mock_order_id", "option_id": option['id'], "entry_price": limit_price, "quantity": contracts, "filled": True}

        try:
            # REAL TRADE - Using limit price for mean reversion entry
            order = r.order_buy_option_limit(
                positionEffect='open',
                creditOrDebit='debit',
                price=limit_price,  # Place limit order at calculated price
                symbol=option['symbol'],
                quantity=contracts,
                expirationDate=option['expiration'],
                strike=option['strike_price'],
                optionType=option['type']
            )
            # Check if order was placed successfully (simplified for demo)
            if order and 'id' in order:
                logger.info(f"✅ Real limit order placed - ID: {order['id']}")
                logger.debug(f"  Note: Order will fill when market reaches ${limit_price:.2f}")
                # Add metadata for monitoring
                order['option_id'] = option['id']
                order['entry_price'] = limit_price  # Use limit price for monitoring
                # If order is not filled immediately, monitoring might be tricky. 
                # For this simple bot, we assume it fills or we monitor limit order. 
                # But to keep it effectively simple, we just pass the order dict.
                return order
            else:
                logger.error(f"Order failed or returned unexpected response: {order}")
                return None

        except Exception as e:
            logger.error(f"Trade failed: {e}")
            return None

    def sell_option(self, trade_details):
        """
        Sells the option at market price (or close to it).
        """
        logger.info(f"💸 Selling position: {trade_details}")
        if not self.is_logged_in():
            logger.info("🎮 Simulation: Position closed")
            return

        try:
            # We need to construct the sell order arguments from the trade details
            # Assuming trade_details contains what we need or we can look it up
            # NOTE: trade_details comes from place_trade return.
            
            # If we have the option_id, we can look up symbol/expiry etc if missing, 
            # but ideally we passed them through. 
            # place_trade (real) returns the order object from robinhood.
            # We might need to fetch the specific instrument details again if they aren't in the order dict.
            
            # Looking at order_buy... arguments, we need symbol, expirationDate, strike, optionType.
            # let's assume we can get these from the original option object or we saved them.
            # The REAL robinhood order dict has a 'instrument' url.
            
            # To be safe/simple, let's fetch the instrument details using the ID we definitely have.
            option_id = trade_details.get('option_id') # We injected this in place_trade
            if not option_id:
                # Fallback if we didn't inject it check 'instrument'
                logger.error("Error: Missing option_id for sell")
                return

            # Retrieve instrument details to be sure
            inst = r.get_option_instrument_data_by_id(option_id)
            symbol = inst['chain_symbol']
            expiration = inst['expiration_date']
            strike = inst['strike_price']
            option_type = inst['type']
            quantity = float(trade_details.get('quantity', 1)) # Default 1 if missing

            # Sell Market/Limit
            # current market price for limit?
            market_data = r.get_option_market_data_by_id(option_id)
            if isinstance(market_data, list): market_data = market_data[0]
            bid_price = float(market_data['adjusted_mark_price']) # using mark as proxy or bid

            logger.info(f"💸 Placing sell order for {symbol} ${strike} {option_type}...")
            r.order_sell_option_limit(
                positionEffect='close',
                creditOrDebit='credit',
                price=bid_price,
                symbol=symbol,
                quantity=quantity,
                expirationDate=expiration,
                strike=strike,
                optionType=option_type
            )
            logger.info("✅ Sell order placed")
            
        except Exception as e:
            logger.error(f"Sell failed: {e}")

    def find_spread_options(self, ticker, decision, budget=1000, target_premium_pct=1.0):
        """
        Finds options for spread strategies (Bull Call Spread or Bear Put Spread).
        Returns dict with 'long_leg' and 'short_leg' option details.
        Returns None if unable to fetch spread options.
        """
        try:
            current_price = float(r.get_latest_price(ticker)[0])
            logger.debug(f"Current price of {ticker}: ${current_price:.2f}")

            option_type = "call" if decision == "BULL_CALL_SPREAD" else "put"

            # Get expiration dates
            chains = r.get_chains(ticker)
            if not chains or 'expiration_dates' not in chains:
                logger.error(f"No option chains found for {ticker}")
                return None

            expirations = chains['expiration_dates']
            valid_dates = [d for d in expirations if d > (datetime.date.today() + datetime.timedelta(days=7)).isoformat()]
            target_date = valid_dates[0] if valid_dates else expirations[-1]

            logger.debug(f"Targeting expiration: {target_date}")

            options = r.find_options_by_expiration(ticker, target_date, optionType=option_type)
            if not options:
                logger.error(f"No {option_type} options found")
                return None

            # Sort by strike
            options.sort(key=lambda x: float(x['strike_price']))

            # Find strikes for spread
            # Bull Call Spread: Buy lower strike call, Sell higher strike call
            # Bear Put Spread: Buy higher strike put, Sell lower strike put

            if decision == "BULL_CALL_SPREAD":
                # Find ATM or slightly ITM call for long leg
                long_options = [o for o in options if float(o['strike_price']) <= current_price * 1.02]
                short_options = [o for o in options if float(o['strike_price']) >= current_price * 1.08]
            else:  # BEAR_PUT_SPREAD
                # Find ATM or slightly ITM put for long leg
                long_options = [o for o in options if float(o['strike_price']) >= current_price * 0.98]
                short_options = [o for o in options if float(o['strike_price']) <= current_price * 0.92]

            if not long_options or not short_options:
                logger.error("Could not find suitable strikes for spread")
                return None

            # Select strikes (closest to target criteria)
            long_option = long_options[-1] if decision == "BULL_CALL_SPREAD" else long_options[0]
            short_option = short_options[0] if decision == "BULL_CALL_SPREAD" else short_options[-1]

            # Get market prices
            long_market_data = r.get_option_market_data_by_id(long_option['id'])
            short_market_data = r.get_option_market_data_by_id(short_option['id'])

            if isinstance(long_market_data, list):
                long_market_data = long_market_data[0]
            if isinstance(short_market_data, list):
                short_market_data = short_market_data[0]

            long_price = float(long_market_data['adjusted_mark_price'])
            short_price = float(short_market_data['adjusted_mark_price'])

            net_debit = long_price - short_price
            limit_price = self.round_option_price(net_debit * target_premium_pct)

            long_strike = float(long_option['strike_price'])
            short_strike = float(short_option['strike_price'])
            max_profit = abs(short_strike - long_strike) - net_debit

            logger.info(f"📈 Spread setup: Long ${long_strike} @ ${long_price:.2f}, Short ${short_strike} @ ${short_price:.2f}")
            logger.debug(f"Net debit: ${net_debit:.2f}, Limit: ${limit_price:.2f}, Max profit: ${max_profit:.2f}")

            return {
                "type": decision,
                "long_leg": {
                    "id": long_option['id'],
                    "symbol": ticker,
                    "strike": long_strike,
                    "strike_price": long_strike,
                    "market_price": long_price,
                    "expiration": long_option.get('expiration_date', target_date)
                },
                "short_leg": {
                    "id": short_option['id'],
                    "symbol": ticker,
                    "strike": short_strike,
                    "strike_price": short_strike,
                    "market_price": short_price,
                    "expiration": short_option.get('expiration_date', target_date)
                },
                "net_debit": net_debit,
                "limit_price": limit_price,
                "max_profit": max_profit,
                "max_loss": net_debit
            }

        except Exception as e:
            logger.error(f"Error finding spread options: {e}")
            import traceback
            logger.exception("Full traceback:")
            return None

    def find_straddle_options(self, ticker, budget=1000, target_premium_pct=1.0):
        """
        Finds ATM call and put for straddle strategy.
        Returns dict with 'call_leg' and 'put_leg' option details.
        Returns None if unable to fetch straddle options.
        """
        try:
            current_price = float(r.get_latest_price(ticker)[0])
            logger.debug(f"Current price of {ticker}: ${current_price:.2f}")

            # Get expiration dates
            chains = r.get_chains(ticker)
            if not chains or 'expiration_dates' not in chains:
                logger.error(f"No option chains found for {ticker}")
                return None

            expirations = chains['expiration_dates']
            valid_dates = [d for d in expirations if d > (datetime.date.today() + datetime.timedelta(days=21)).isoformat()]
            target_date = valid_dates[0] if valid_dates else expirations[-1]

            logger.debug(f"Targeting expiration: {target_date}")

            # Get ATM calls and puts
            call_options = r.find_options_by_expiration(ticker, target_date, optionType="call")
            put_options = r.find_options_by_expiration(ticker, target_date, optionType="put")

            if not call_options or not put_options:
                logger.error("Could not find call or put options")
                return None

            # Find ATM strike (closest to current price)
            call_options.sort(key=lambda x: abs(float(x['strike_price']) - current_price))
            put_options.sort(key=lambda x: abs(float(x['strike_price']) - current_price))

            atm_call = call_options[0]
            atm_put = put_options[0]

            # Get market prices
            call_market_data = r.get_option_market_data_by_id(atm_call['id'])
            put_market_data = r.get_option_market_data_by_id(atm_put['id'])

            if isinstance(call_market_data, list):
                call_market_data = call_market_data[0]
            if isinstance(put_market_data, list):
                put_market_data = put_market_data[0]

            call_price = float(call_market_data['adjusted_mark_price'])
            put_price = float(put_market_data['adjusted_mark_price'])

            total_debit = call_price + put_price
            limit_price = self.round_option_price(total_debit * target_premium_pct)

            strike = float(atm_call['strike_price'])
            breakeven_up = strike + total_debit
            breakeven_down = strike - total_debit

            logger.info(f"📊 Straddle setup: Strike ${strike}, Call @ ${call_price:.2f}, Put @ ${put_price:.2f}")
            logger.debug(f"Total debit: ${total_debit:.2f}, Limit: ${limit_price:.2f}")
            logger.debug(f"Breakevens: ${breakeven_down:.2f} / ${breakeven_up:.2f}")

            return {
                "type": "STRADDLE",
                "call_leg": {
                    "id": atm_call['id'],
                    "symbol": ticker,
                    "strike": strike,
                    "strike_price": strike,
                    "market_price": call_price,
                    "expiration": atm_call.get('expiration_date', target_date)
                },
                "put_leg": {
                    "id": atm_put['id'],
                    "symbol": ticker,
                    "strike": strike,
                    "strike_price": strike,
                    "market_price": put_price,
                    "expiration": atm_put.get('expiration_date', target_date)
                },
                "total_debit": total_debit,
                "limit_price": limit_price,
                "breakeven_up": breakeven_up,
                "breakeven_down": breakeven_down
            }

        except Exception as e:
            logger.error(f"Error finding straddle options: {e}")
            import traceback
            logger.exception("Full traceback:")
            return None


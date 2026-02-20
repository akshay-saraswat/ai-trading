import pandas_market_calendars as mcal
from datetime import datetime, time, timedelta
import pytz


class MarketSchedule:
    """
    Handles market schedule logic for NYSE trading hours.
    Market is open Monday-Friday 9:30 AM - 4:00 PM ET, excluding holidays.
    """

    def __init__(self, timezone='America/New_York'):
        """
        Initialize market schedule with NYSE calendar.

        Args:
            timezone: Timezone string (default: America/New_York)
        """
        self.tz = pytz.timezone(timezone)
        self.nyse = mcal.get_calendar('NYSE')

        # Market hours in Eastern Time
        self.market_open_time = time(9, 30)  # 9:30 AM
        self.market_close_time = time(16, 0)  # 4:00 PM

    def is_market_open_for_new_trades(self) -> bool:
        """
        Check if the market is currently open for new trades.

        Returns:
            True if current time is during NYSE trading hours (9:30 AM - 4:00 PM ET)
            on a trading day (weekday, not holiday), False otherwise.
            If settings.SKIP_MARKET_SCHEDULE_CHECK is True, always returns True (for testing).
            If settings.BLOCK_FIRST_HOUR_TRADING is True, blocks trades during 9:30-10:30 AM ET.
        """
        # Import here to avoid circular dependency and to get latest value
        from backend.config import settings

        # If skip flag is set, always return True (for testing outside market hours)
        if settings.SKIP_MARKET_SCHEDULE_CHECK:
            return True

        now = datetime.now(self.tz)

        # Get today's schedule
        schedule = self.nyse.schedule(
            start_date=now.date(),
            end_date=now.date()
        )

        # If schedule is empty, market is not open today (weekend or holiday)
        if schedule.empty:
            return False

        # Get market open and close times for today
        market_open = schedule.iloc[0]['market_open'].tz_convert(self.tz)
        market_close = schedule.iloc[0]['market_close'].tz_convert(self.tz)

        # Check if current time is between market open and close
        if not (market_open <= now <= market_close):
            return False

        # If first hour trading is blocked, check if we're in the first hour (9:30-10:30 AM ET)
        if settings.BLOCK_FIRST_HOUR_TRADING:
            first_hour_end = market_open + timedelta(hours=1)
            if now < first_hour_end:
                return False

        return True

    def get_next_market_open(self) -> datetime:
        """
        Get the next market open datetime.

        Returns:
            Datetime object representing the next market open time in Eastern Time.
        """
        now = datetime.now(self.tz)

        # Get schedule for next 10 days to find next trading day
        schedule = self.nyse.schedule(
            start_date=now.date(),
            end_date=(now + timedelta(days=10)).date()
        )

        if schedule.empty:
            # Shouldn't happen, but return a fallback
            return now + timedelta(days=1)

        # Find the next market open
        for idx, row in schedule.iterrows():
            market_open = row['market_open'].tz_convert(self.tz)
            if market_open > now:
                return market_open

        # If we get here, return first item in schedule
        return schedule.iloc[0]['market_open'].tz_convert(self.tz)


if __name__ == "__main__":
    # Test the market schedule
    ms = MarketSchedule()

    print("Market Schedule Status:")
    print(f"Is market open for new trades: {ms.is_market_open_for_new_trades()}")
    print(f"Is trading day: {ms.is_trading_day()}")
    print(f"Next market open: {ms.get_next_market_open().strftime('%A, %B %d, %Y at %I:%M %p %Z')}")
    print(f"Time until market open: {ms.get_time_until_market_open()}")

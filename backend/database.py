"""
SQLite database for persistence
Stores positions, trades, and settings
"""
import aiosqlite
import json
from typing import List, Dict, Optional
from datetime import datetime
import logging
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Connect to database and create tables"""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"✅ Connected to database: {self.db_path}")

    async def disconnect(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()

    async def _create_tables(self):
        """Create database schema with multi-tenancy support"""
        # Sessions table for persistent authentication
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                device_token TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                logged_in INTEGER DEFAULT 1
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default_user',
                ticker TEXT NOT NULL,
                decision TEXT NOT NULL,
                option_id TEXT,
                strike REAL NOT NULL,
                expiration TEXT NOT NULL,
                contracts INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                take_profit REAL NOT NULL,
                stop_loss REAL NOT NULL,
                source TEXT DEFAULT 'bot',
                strategy_used TEXT DEFAULT 'none',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT DEFAULT 'open'
            )
        ''')

        # Create indexes for performance
        await self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions(user_id)
        ''')
        await self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_positions_user_status ON positions(user_id, status)
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default_user',
                position_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                contracts INTEGER NOT NULL,
                pnl REAL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (position_id) REFERENCES positions(id)
            )
        ''')

        await self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        ''')

        await self.conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings(user_id)
        ''')

        await self.conn.commit()

    # ========== Position Management ==========

    async def create_position(self, position: Dict, user_id: str) -> str:
        """Create new position for specific user"""
        now = datetime.now().isoformat()
        position_id = position['id']

        await self.conn.execute('''
            INSERT INTO positions (
                id, user_id, ticker, decision, option_id, strike, expiration,
                contracts, entry_price, take_profit, stop_loss, source,
                strategy_used, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position_id,
            user_id,
            position['ticker'],
            position['decision'],
            position.get('option_id'),
            position['strike'],
            position['expiration'],
            position['contracts'],
            position['entry_price'],
            position['take_profit'],
            position['stop_loss'],
            position.get('source', 'bot'),
            position.get('strategy_used', 'none'),
            now,
            now,
            'open'
        ))
        await self.conn.commit()
        logger.info(f"Created position for {user_id}: {position_id} - {position['ticker']}")
        return position_id

    async def get_position(self, position_id: str, user_id: str) -> Optional[Dict]:
        """Get position by ID for specific user"""
        cursor = await self.conn.execute(
            'SELECT * FROM positions WHERE id = ? AND user_id = ?',
            (position_id, user_id)
        )
        row = await cursor.fetchone()

        if row:
            return dict(row)
        return None

    async def get_position_any_user(self, position_id: str) -> Optional[Dict]:
        """Get position by ID without user filtering (for internal background services)"""
        cursor = await self.conn.execute(
            'SELECT * FROM positions WHERE id = ?',
            (position_id,)
        )
        row = await cursor.fetchone()

        if row:
            return dict(row)
        return None

    async def get_open_positions(self, user_id: str) -> List[Dict]:
        """Get all open positions for specific user"""
        cursor = await self.conn.execute(
            "SELECT * FROM positions WHERE user_id = ? AND status = 'open' ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_position(self, position_id: str, user_id: str, updates: Dict):
        """Update position fields for specific user"""
        updates['updated_at'] = datetime.now().isoformat()

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [position_id, user_id]

        await self.conn.execute(
            f'UPDATE positions SET {set_clause} WHERE id = ? AND user_id = ?',
            values
        )
        await self.conn.commit()

    async def close_position(self, position_id: str, user_id: str, exit_price: float, reason: str = None):
        """Close position and record trade for specific user"""
        position = await self.get_position(position_id, user_id)
        if not position:
            raise ValueError(f"Position not found: {position_id}")

        # Calculate P&L
        pnl = (exit_price - position['entry_price']) * position['contracts'] * 100

        # Update position status
        await self.update_position(position_id, user_id, {'status': 'closed'})

        # Record trade
        await self.record_trade(
            user_id=user_id,
            position_id=position_id,
            ticker=position['ticker'],
            action='SELL',
            price=exit_price,
            contracts=position['contracts'],
            pnl=pnl,
            reason=reason
        )

        logger.info(f"Closed position for {user_id}: {position_id} - P&L: ${pnl:.2f}")

    async def record_trade(
        self,
        user_id: str,
        position_id: str,
        ticker: str,
        action: str,
        price: float,
        contracts: int,
        pnl: Optional[float] = None,
        reason: Optional[str] = None
    ):
        """Record trade history for specific user"""
        await self.conn.execute('''
            INSERT INTO trades (
                user_id, position_id, ticker, action, price, contracts, pnl, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            position_id,
            ticker,
            action,
            price,
            contracts,
            pnl,
            reason,
            datetime.now().isoformat()
        ))
        await self.conn.commit()

    async def get_trade_history(self, user_id: str, limit: int = 100) -> List[Dict]:
        """Get trade history for specific user"""
        cursor = await self.conn.execute(
            'SELECT * FROM trades WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ========== Settings Management ==========

    async def get_performance_stats(self, user_id: str) -> Dict:
        """Calculate performance statistics for specific user"""
        # Total P&L
        cursor = await self.conn.execute(
            'SELECT SUM(pnl) as total_pnl, COUNT(*) as total_trades FROM trades WHERE user_id = ? AND pnl IS NOT NULL',
            (user_id,)
        )
        row = await cursor.fetchone()

        total_pnl = row['total_pnl'] or 0
        total_trades = row['total_trades'] or 0

        # Win rate
        cursor = await self.conn.execute(
            'SELECT COUNT(*) as wins FROM trades WHERE user_id = ? AND pnl > 0',
            (user_id,)
        )
        wins = (await cursor.fetchone())['wins']

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # Average P&L
        avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0

        return {
            'total_pnl': total_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_pnl': avg_pnl
        }

    async def get_settings(self, user_id: str) -> Optional[Dict]:
        """
        Get application settings from database for specific user.
        Returns None if no settings exist.
        """
        try:
            cursor = await self.conn.execute(
                'SELECT value FROM settings WHERE user_id = ? AND key = ?',
                (user_id, 'app_settings')
            )
            row = await cursor.fetchone()

            if row:
                return json.loads(row['value'])
            return None

        except Exception as e:
            logger.error(f"Error getting settings for {user_id}: {e}")
            return None

    async def save_settings(self, user_id: str, settings_data: Dict):
        """
        Save application settings to database for specific user.
        """
        try:
            settings_json = json.dumps(settings_data)
            now = datetime.utcnow().isoformat()

            await self.conn.execute('''
                INSERT OR REPLACE INTO settings (user_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 'app_settings', settings_json, now))

            await self.conn.commit()
            logger.info(f"Settings saved for {user_id}")

        except Exception as e:
            logger.error(f"Error saving settings for {user_id}: {e}")
            raise


# Global database instance
db = Database()

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
        """Create database schema"""
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT DEFAULT 'open'
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        await self.conn.commit()

    # ========== Position Management ==========

    async def create_position(self, position: Dict) -> str:
        """Create new position"""
        now = datetime.now().isoformat()
        position_id = position['id']

        await self.conn.execute('''
            INSERT INTO positions (
                id, ticker, decision, option_id, strike, expiration,
                contracts, entry_price, take_profit, stop_loss, source,
                created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position_id,
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
            now,
            now,
            'open'
        ))
        await self.conn.commit()
        logger.info(f"Created position: {position_id} - {position['ticker']}")
        return position_id

    async def get_position(self, position_id: str) -> Optional[Dict]:
        """Get position by ID"""
        cursor = await self.conn.execute(
            'SELECT * FROM positions WHERE id = ?',
            (position_id,)
        )
        row = await cursor.fetchone()

        if row:
            return dict(row)
        return None

    async def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        cursor = await self.conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_position(self, position_id: str, updates: Dict):
        """Update position fields"""
        updates['updated_at'] = datetime.now().isoformat()

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [position_id]

        await self.conn.execute(
            f'UPDATE positions SET {set_clause} WHERE id = ?',
            values
        )
        await self.conn.commit()

    async def close_position(self, position_id: str, exit_price: float, reason: str = None):
        """Close position and record trade"""
        position = await self.get_position(position_id)
        if not position:
            raise ValueError(f"Position not found: {position_id}")

        # Calculate P&L
        pnl = (exit_price - position['entry_price']) * position['contracts'] * 100

        # Update position status
        await self.update_position(position_id, {'status': 'closed'})

        # Record trade
        await self.record_trade(
            position_id=position_id,
            ticker=position['ticker'],
            action='SELL',
            price=exit_price,
            contracts=position['contracts'],
            pnl=pnl,
            reason=reason
        )

        logger.info(f"Closed position: {position_id} - P&L: ${pnl:.2f}")

    async def record_trade(
        self,
        position_id: str,
        ticker: str,
        action: str,
        price: float,
        contracts: int,
        pnl: Optional[float] = None,
        reason: Optional[str] = None
    ):
        """Record trade history"""
        await self.conn.execute('''
            INSERT INTO trades (
                position_id, ticker, action, price, contracts, pnl, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
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

    async def get_trade_history(self, limit: int = 100) -> List[Dict]:
        """Get trade history"""
        cursor = await self.conn.execute(
            'SELECT * FROM trades ORDER BY created_at DESC LIMIT ?',
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ========== Settings Management ==========

    async def get_setting(self, key: str) -> Optional[str]:
        """Get setting value"""
        cursor = await self.conn.execute(
            'SELECT value FROM settings WHERE key = ?',
            (key,)
        )
        row = await cursor.fetchone()
        return row['value'] if row else None

    async def set_setting(self, key: str, value: str):
        """Set setting value"""
        await self.conn.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
        await self.conn.commit()

    async def get_all_settings(self) -> Dict:
        """Get all settings as dict"""
        cursor = await self.conn.execute('SELECT key, value FROM settings')
        rows = await cursor.fetchall()
        return {row['key']: row['value'] for row in rows}

    # ========== Analytics ==========

    async def get_performance_stats(self) -> Dict:
        """Calculate performance statistics"""
        # Total P&L
        cursor = await self.conn.execute(
            'SELECT SUM(pnl) as total_pnl, COUNT(*) as total_trades FROM trades WHERE pnl IS NOT NULL'
        )
        row = await cursor.fetchone()

        total_pnl = row['total_pnl'] or 0
        total_trades = row['total_trades'] or 0

        # Win rate
        cursor = await self.conn.execute(
            'SELECT COUNT(*) as wins FROM trades WHERE pnl > 0'
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

    async def get_settings(self) -> Optional[Dict]:
        """
        Get application settings from database.
        Returns None if no settings exist.
        """
        try:
            cursor = await self.conn.execute(
                'SELECT value FROM settings WHERE key = ?',
                ('app_settings',)
            )
            row = await cursor.fetchone()

            if row:
                return json.loads(row['value'])
            return None

        except Exception as e:
            logger.error(f"Error getting settings: {e}")
            return None

    async def save_settings(self, settings_data: Dict):
        """
        Save application settings to database.
        """
        try:
            settings_json = json.dumps(settings_data)
            now = datetime.utcnow().isoformat()

            await self.conn.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', ('app_settings', settings_json, now))

            await self.conn.commit()
            logger.info("Settings saved to database")

        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            raise


# Global database instance
db = Database()

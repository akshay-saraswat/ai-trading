#!/usr/bin/env python3
"""
Database migration script to add user_id column to existing tables.
Run this once to upgrade your database schema for multi-tenancy support.

Usage:
    python migrate_database.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = "data/trading.db"


def migrate():
    """Add user_id column to positions and trades tables if it doesn't exist"""
    print(f"🔧 Migrating database: {DB_PATH}")

    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        print("   No migration needed - database will be created with correct schema on first run.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if user_id column exists in positions table
        cursor.execute("PRAGMA table_info(positions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'user_id' not in columns:
            print("📝 Adding user_id column to positions table...")
            cursor.execute("ALTER TABLE positions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default_user'")
            print("✅ Added user_id column to positions")
        else:
            print("✓ user_id column already exists in positions")

        # Check if user_id column exists in trades table
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'user_id' not in columns:
            print("📝 Adding user_id column to trades table...")
            cursor.execute("ALTER TABLE trades ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default_user'")
            print("✅ Added user_id column to trades")
        else:
            print("✓ user_id column already exists in trades")

        # Create indexes
        print("📝 Creating indexes...")
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_user_id ON positions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_user_status ON positions(user_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings(user_id)")
            print("✅ Indexes created")
        except Exception as e:
            print(f"⚠️  Index creation warning: {e}")

        conn.commit()
        print("✅ Migration complete!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()

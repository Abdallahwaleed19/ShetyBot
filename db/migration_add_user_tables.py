"""
db/migration_add_user_tables.py — Add user management tables
Run this to create the new tables: users, verification_codes
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from db.database import engine


async def migrate():
    """Create new tables for user management"""
    async with engine.begin() as conn:
        # Create users table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                telegram_user_id VARCHAR(50) NOT NULL UNIQUE,
                username VARCHAR(100),
                role ENUM('user', 'admin') NOT NULL DEFAULT 'user',
                subscription_start DATETIME,
                subscription_end DATETIME,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_telegram_user_id (telegram_user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))

        # Create verification_codes table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS verification_codes (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                code_hash VARCHAR(100) NOT NULL,
                expires_at DATETIME NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_expires_at (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))

        # Add user_id column to sick_leave_reports if it doesn't exist
        try:
            await conn.execute(text("""
                ALTER TABLE sick_leave_reports
                ADD COLUMN user_id BIGINT NOT NULL DEFAULT 0 AFTER relationship,
                ADD INDEX idx_user_id (user_id)
            """))
            print("✅ Added user_id column to sick_leave_reports")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("ℹ️  user_id column already exists in sick_leave_reports")
            else:
                print(f"⚠️  Warning adding user_id: {e}")

        # Create default admin user (telegram_user_id = "admin")
        await conn.execute(text("""
            INSERT IGNORE INTO users (telegram_user_id, username, role, is_active)
            VALUES ('admin', 'Admin', 'admin', TRUE)
        """))

        print("✅ Migration completed successfully!")
        print("📝 Default admin user created with telegram_user_id='admin'")


if __name__ == "__main__":
    asyncio.run(migrate())

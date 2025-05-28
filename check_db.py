"""Script to check database contents."""

import asyncio
from sqlalchemy import text
from src.db.connection import init_db

async def check_database():
    """Check database contents."""
    # Initialize database
    db = init_db()
    
    async with db.session() as session:
        # Check signals table
        result = await session.execute(text("SELECT COUNT(*) FROM signals"))
        count = result.scalar()
        print(f"Total signals: {count}")
        
        if count > 0:
            # Get latest signals
            result = await session.execute(
                text("SELECT id, symbol, direction, status, created_at FROM signals ORDER BY created_at DESC LIMIT 5")
            )
            rows = result.fetchall()
            print("\nLatest signals:")
            for row in rows:
                print(f"ID: {row[0]}, Symbol: {row[1]}, Direction: {row[2]}, Status: {row[3]}, Created: {row[4]}")

if __name__ == "__main__":
    asyncio.run(check_database()) 
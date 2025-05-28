# Database Migrations Guide

This guide explains how to manage database migrations in the Telecopier project using Alembic.

## Prerequisites

1. Make sure you have all dependencies installed:
```bash
pip install alembic sqlalchemy psycopg2-binary python-dotenv
```

2. Ensure your `.env` file contains the database URL:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/telecopier
```

## Initial Setup

If you're setting up migrations for the first time:

1. Initialize Alembic:
```bash
python -m alembic init alembic
```

2. Configure `alembic/env.py`:
```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from dotenv import load_dotenv

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Import all models for Alembic to detect
from src.db.models.base import Base
from src.db.models.signal import Signal
from src.db.models.trade import Trade  # Import other models as needed

config = context.config

# Get database URL from environment and convert to synchronous URL for migrations
db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/telecopier")
sync_url = db_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)

# Set target metadata
target_metadata = Base.metadata
```

3. Configure `alembic.ini`:
   - Set `script_location = alembic`
   - Leave `sqlalchemy.url` empty (it's set in env.py)

## Creating New Migrations

1. Make changes to your SQLAlchemy models in `src/db/models/`

2. Create a new migration:
```bash
python -m alembic revision --autogenerate -m "description_of_changes"
```

3. The migration will be created in `alembic/versions/`

4. Review the generated migration file to ensure it captures your intended changes

## Applying Migrations

1. Apply all pending migrations:
```bash
python -m alembic upgrade head
```

2. Apply to a specific revision:
```bash
python -m alembic upgrade <revision_id>
```

## Rolling Back Migrations

1. Rollback one migration:
```bash
python -m alembic downgrade -1
```

2. Rollback to a specific revision:
```bash
python -m alembic downgrade <revision_id>
```

## Checking Migration Status

1. View migration history:
```bash
python -m alembic history
```

2. Check current revision:
```bash
python -m alembic current
```

## Common Issues and Solutions

### 1. AsyncPG Issues
If you see errors about greenlets or async operations, make sure you're using the synchronous database URL for migrations. The `env.py` script should convert the async URL:
```python
sync_url = db_url.replace("+asyncpg", "")
```

### 2. Import Errors
If you see import errors, check that:
- The project root is in the Python path
- All models are imported in `env.py`
- All model dependencies are satisfied

### 3. Database Connection Issues
- Verify your database is running
- Check the DATABASE_URL in your `.env` file
- Ensure you have the correct permissions

## Best Practices

1. **Always Review Migrations**: Before applying, review the generated migration files

2. **Backup Your Database**: Always backup before running migrations in production

3. **Test Migrations**: Test both upgrade and downgrade paths in development

4. **Version Control**: Keep migrations in version control with your code

5. **Meaningful Messages**: Use descriptive messages when creating migrations

## Example: Modifying Column Type

Here's an example of changing a column type:

1. Update the model:
```python
chat_id: Mapped[int] = mapped_column(
    BigInteger,  # Changed from Integer
    nullable=False,
    index=True
)
```

2. Create migration:
```bash
python -m alembic revision --autogenerate -m "update_chat_id_to_bigint"
```

3. Apply migration:
```bash
python -m alembic upgrade head
```

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/) 
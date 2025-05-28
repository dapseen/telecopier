"""Database migration management script.

This script provides commands for managing database migrations:
- Create new migrations
- Apply migrations
- Rollback migrations
- Show migration history
"""

import argparse
import logging
import os
import sys
from typing import Optional

import alembic
from alembic.config import Config
from alembic.script import ScriptDirectory

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_alembic_config() -> Config:
    """Get Alembic configuration.
    
    Returns:
        Config: Alembic configuration
    """
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Get the project root directory
    project_root = os.path.dirname(script_dir)
    # Path to alembic.ini
    alembic_ini = os.path.join(project_root, "alembic.ini")
    
    return Config(alembic_ini)

def get_current_revision() -> Optional[str]:
    """Get current database revision.
    
    Returns:
        Optional[str]: Current revision if any
    """
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    
    try:
        with alembic.context.EnvironmentContext(
            config,
            script
        ) as env:
            with env.begin_transaction():
                return env.get_head_revision()
    except Exception as e:
        logger.error(f"Failed to get current revision: {e}")
        return None

def create_migration(message: str) -> None:
    """Create a new migration.
    
    Args:
        message: Migration message
    """
    try:
        config = get_alembic_config()
        alembic.command.revision(
            config,
            message=message,
            autogenerate=True
        )
        logger.info(f"Created new migration: {message}")
    except Exception as e:
        logger.error(f"Failed to create migration: {e}")
        raise

def upgrade_migrations(revision: str = "head") -> None:
    """Upgrade database to a specific revision.
    
    Args:
        revision: Target revision (default: "head")
    """
    try:
        config = get_alembic_config()
        alembic.command.upgrade(config, revision)
        logger.info(f"Upgraded database to revision: {revision}")
    except Exception as e:
        logger.error(f"Failed to upgrade database: {e}")
        raise

def downgrade_migrations(revision: str) -> None:
    """Downgrade database to a specific revision.
    
    Args:
        revision: Target revision
    """
    try:
        config = get_alembic_config()
        alembic.command.downgrade(config, revision)
        logger.info(f"Downgraded database to revision: {revision}")
    except Exception as e:
        logger.error(f"Failed to downgrade database: {e}")
        raise

def show_migration_history() -> None:
    """Show migration history."""
    try:
        config = get_alembic_config()
        alembic.command.history(config)
    except Exception as e:
        logger.error(f"Failed to show migration history: {e}")
        raise

def main() -> None:
    """Main entry point for migration management."""
    parser = argparse.ArgumentParser(
        description="Manage database migrations"
    )
    subparsers = parser.add_subparsers(dest="command")
    
    # Create migration command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new migration"
    )
    create_parser.add_argument(
        "message",
        help="Migration message"
    )
    
    # Upgrade command
    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Upgrade database to a specific revision"
    )
    upgrade_parser.add_argument(
        "--revision",
        default="head",
        help="Target revision (default: head)"
    )
    
    # Downgrade command
    downgrade_parser = subparsers.add_parser(
        "downgrade",
        help="Downgrade database to a specific revision"
    )
    downgrade_parser.add_argument(
        "revision",
        help="Target revision"
    )
    
    # History command
    subparsers.add_parser(
        "history",
        help="Show migration history"
    )
    
    args = parser.parse_args()
    
    if args.command == "create":
        create_migration(args.message)
    elif args.command == "upgrade":
        upgrade_migrations(args.revision)
    elif args.command == "downgrade":
        downgrade_migrations(args.revision)
    elif args.command == "history":
        show_migration_history()
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 
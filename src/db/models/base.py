"""Base model and common fields for database models.

This module provides:
- Base model class with common fields
- Common field types
- Model utilities
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Base class for all database models.
    
    Provides common fields and functionality for all models:
    - UUID primary key
    - Created/updated timestamps
    - Soft delete support
    - Audit fields
    """
    
    # Common fields for all models
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model instance to dictionary.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the model
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Base":
        """Create model instance from dictionary.
        
        Args:
            data: Dictionary containing model data
            
        Returns:
            Base: Model instance
        """
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__table__.columns.keys()
        })
        
    def update(self, data: Dict[str, Any]) -> None:
        """Update model instance with dictionary data.
        
        Args:
            data: Dictionary containing update data
        """
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
    def soft_delete(self) -> None:
        """Mark model instance as deleted."""
        self.deleted_at = datetime.now(timezone=True)
        
    def restore(self) -> None:
        """Restore soft-deleted model instance."""
        self.deleted_at = None 
"""Base repository class with common database operations.

This module provides:
- Base repository class with CRUD operations
- Common query methods
- Transaction management
- Error handling
"""

from datetime import datetime
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    Union
)
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.db.models.base import Base

# Type variable for model class
ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """Base repository class with common database operations.
    
    This class provides:
    - CRUD operations
    - Common query methods
    - Transaction management
    - Error handling
    
    Args:
        model: SQLAlchemy model class
        session: Database session
    """
    
    def __init__(
        self,
        model: Type[ModelType],
        session: AsyncSession
    ):
        """Initialize repository.
        
        Args:
            model: SQLAlchemy model class
            session: Database session
        """
        self.model = model
        self.session = session
        
    async def create(self, obj_in: Dict[str, Any]) -> ModelType:
        """Create new record.
        
        Args:
            obj_in: Dictionary with model data
            
        Returns:
            ModelType: Created model instance
        """
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj
        
    async def get(self, id: UUID) -> Optional[ModelType]:
        """Get record by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[ModelType]: Model instance if found
        """
        return await self.session.get(self.model, id)
        
    async def get_multi(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        query: Optional[Select] = None
    ) -> List[ModelType]:
        """Get multiple records.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            query: Custom query to use
            
        Returns:
            List[ModelType]: List of model instances
        """
        if query is None:
            query = select(self.model)
            
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
        
    async def update(
        self,
        *,
        db_obj: ModelType,
        obj_in: Union[Dict[str, Any], ModelType]
    ) -> ModelType:
        """Update record.
        
        Args:
            db_obj: Database object to update
            obj_in: Dictionary or model instance with update data
            
        Returns:
            ModelType: Updated model instance
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.to_dict()
            
        for field in update_data:
            if hasattr(db_obj, field):
                setattr(db_obj, field, update_data[field])
                
        db_obj.updated_at = datetime.now(timezone=True)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj
        
    async def delete(self, *, id: UUID) -> Optional[ModelType]:
        """Delete record by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[ModelType]: Deleted model instance if found
        """
        obj = await self.get(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()
        return obj
        
    async def soft_delete(self, *, id: UUID) -> Optional[ModelType]:
        """Soft delete record by ID.
        
        Args:
            id: Record ID
            
        Returns:
            Optional[ModelType]: Updated model instance if found
        """
        obj = await self.get(id)
        if obj:
            obj.soft_delete()
            await self.session.flush()
            await self.session.refresh(obj)
        return obj
        
    async def exists(self, id: UUID) -> bool:
        """Check if record exists.
        
        Args:
            id: Record ID
            
        Returns:
            bool: True if record exists
        """
        query = select(self.model).where(self.model.id == id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None
        
    async def count(
        self,
        *,
        query: Optional[Select] = None
    ) -> int:
        """Count records.
        
        Args:
            query: Custom query to use
            
        Returns:
            int: Number of records
        """
        if query is None:
            query = select(self.model)
            
        result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        return result.scalar_one()
        
    def _build_query(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        include_deleted: bool = False
    ) -> Select:
        """Build query with filters and ordering.
        
        Args:
            filters: Dictionary of field filters
            order_by: List of fields to order by
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            Select: SQLAlchemy select query
        """
        query = select(self.model)
        
        # Apply filters
        if filters:
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(
                        getattr(self.model, field) == value
                    )
                    
        # Handle soft deletes
        if not include_deleted and hasattr(self.model, "deleted_at"):
            query = query.where(self.model.deleted_at.is_(None))
            
        # Apply ordering
        if order_by:
            for field in order_by:
                if hasattr(self.model, field):
                    query = query.order_by(getattr(self.model, field))
                    
        return query
        
    async def get_by_filters(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False
    ) -> List[ModelType]:
        """Get records by filters.
        
        Args:
            filters: Dictionary of field filters
            order_by: List of fields to order by
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            List[ModelType]: List of model instances
        """
        query = self._build_query(
            filters=filters,
            order_by=order_by,
            include_deleted=include_deleted
        )
        return await self.get_multi(
            skip=skip,
            limit=limit,
            query=query
        )
        
    async def get_one_by_filters(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        include_deleted: bool = False
    ) -> Optional[ModelType]:
        """Get single record by filters.
        
        Args:
            filters: Dictionary of field filters
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            Optional[ModelType]: Model instance if found
        """
        query = self._build_query(
            filters=filters,
            include_deleted=include_deleted
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
        
    async def update_by_filters(
        self,
        *,
        filters: Dict[str, Any],
        update_data: Dict[str, Any],
        include_deleted: bool = False
    ) -> List[ModelType]:
        """Update records by filters.
        
        Args:
            filters: Dictionary of field filters
            update_data: Dictionary with update data
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            List[ModelType]: List of updated model instances
        """
        query = self._build_query(
            filters=filters,
            include_deleted=include_deleted
        )
        result = await self.session.execute(query)
        objs = list(result.scalars().all())
        
        for obj in objs:
            await self.update(db_obj=obj, obj_in=update_data)
            
        return objs
        
    async def delete_by_filters(
        self,
        *,
        filters: Dict[str, Any],
        include_deleted: bool = False
    ) -> List[ModelType]:
        """Delete records by filters.
        
        Args:
            filters: Dictionary of field filters
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            List[ModelType]: List of deleted model instances
        """
        query = self._build_query(
            filters=filters,
            include_deleted=include_deleted
        )
        result = await self.session.execute(query)
        objs = list(result.scalars().all())
        
        for obj in objs:
            await self.session.delete(obj)
            
        await self.session.flush()
        return objs
        
    async def soft_delete_by_filters(
        self,
        *,
        filters: Dict[str, Any],
        include_deleted: bool = False
    ) -> List[ModelType]:
        """Soft delete records by filters.
        
        Args:
            filters: Dictionary of field filters
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            List[ModelType]: List of updated model instances
        """
        query = self._build_query(
            filters=filters,
            include_deleted=include_deleted
        )
        result = await self.session.execute(query)
        objs = list(result.scalars().all())
        
        for obj in objs:
            obj.soft_delete()
            
        await self.session.flush()
        return objs 
"""Statistics router for managing trading statistics.

This module provides endpoints for:
- Creating statistics records
- Retrieving statistics
- Analyzing trading performance
"""

from typing import List, Optional
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query

from src.db.repositories.statistics import StatisticsRepository
from ..dependencies import get_statistics_repository
from ..models import StatisticsCreate, StatisticsResponse

router = APIRouter()

@router.post("/", response_model=StatisticsResponse)
async def create_statistics(
    stats: StatisticsCreate,
    repo: StatisticsRepository = Depends(get_statistics_repository)
) -> StatisticsResponse:
    """Create a new statistics record.
    
    Args:
        stats: Statistics data
        repo: Statistics repository
        
    Returns:
        StatisticsResponse: Created statistics record
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        db_stats = await repo.create(stats.model_dump())
        return StatisticsResponse.model_validate(db_stats)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create statistics record: {str(e)}"
        )

@router.get("/{stats_id}", response_model=StatisticsResponse)
async def get_statistics(
    stats_id: UUID,
    repo: StatisticsRepository = Depends(get_statistics_repository)
) -> StatisticsResponse:
    """Get statistics by ID.
    
    Args:
        stats_id: Statistics ID
        repo: Statistics repository
        
    Returns:
        StatisticsResponse: Statistics data
        
    Raises:
        HTTPException: If not found
    """
    stats = await repo.get(stats_id)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail="Statistics record not found"
        )
    return StatisticsResponse.model_validate(stats)

@router.get("/", response_model=List[StatisticsResponse])
async def list_statistics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    repo: StatisticsRepository = Depends(get_statistics_repository)
) -> List[StatisticsResponse]:
    """List statistics with optional date filtering.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        start_date: Filter by start date
        end_date: Filter by end date
        repo: Statistics repository
        
    Returns:
        List[StatisticsResponse]: List of statistics records
    """
    filters = {}
    if start_date:
        filters["trading_date__gte"] = start_date
    if end_date:
        filters["trading_date__lte"] = end_date
        
    stats = await repo.get_multi(
        skip=skip,
        limit=limit,
        filters=filters
    )
    return [StatisticsResponse.model_validate(s) for s in stats]

@router.get("/summary", response_model=StatisticsResponse)
async def get_summary_statistics(
    start_date: date,
    end_date: date,
    repo: StatisticsRepository = Depends(get_statistics_repository)
) -> StatisticsResponse:
    """Get summary statistics for a date range.
    
    Args:
        start_date: Start date
        end_date: End date
        repo: Statistics repository
        
    Returns:
        StatisticsResponse: Aggregated statistics
        
    Raises:
        HTTPException: If calculation fails
    """
    try:
        summary = await repo.get_summary_statistics(
            start_date=start_date,
            end_date=end_date
        )
        return StatisticsResponse.model_validate(summary)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to calculate summary statistics: {str(e)}"
        ) 
"""
WorkLog Settlement System - API Endpoints

REST API endpoints for worklog listing and remittance generation.
Implements senior developer best practices:
- Service layer separation
- Proper authentication
- Comprehensive documentation
- Type safety with Pydantic
"""
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, get_current_active_superuser
from app.api.routes.worklog.schemas import (
    GenerateRemittancesRequest,
    GenerateRemittancesResponse,
    WorkLogsPublic,
)
from app.api.routes.worklog.service import WorkLogService

router = APIRouter(prefix="/worklogs", tags=["worklogs"])


@router.get(
    "/list-all-worklogs",
    response_model=WorkLogsPublic,
    summary="List all worklogs with amounts",
    description="""
    Lists all worklogs with calculated amounts and filtering options.
    
    Each worklog includes:
    - Time segments with their settlement status
    - Adjustments (bonuses/deductions)
    - Calculated amounts (remitted, unremitted, total)
    - Overall remittance status
    
    **Filtering:**
    - `remittanceStatus=REMITTED`: Only fully paid worklogs
    - `remittanceStatus=UNREMITTED`: Worklogs with unpaid amounts
    """,
)
def list_all_worklogs(
    session: SessionDep,
    remittanceStatus: str | None = Query(
        default=None,
        description="Filter by remittance status: REMITTED or UNREMITTED",
        examples=["REMITTED", "UNREMITTED"],
    ),
) -> Any:
    """
    List all worklogs with filtering and amount information.
    
    Returns worklogs with their time segments, adjustments, and
    calculated amounts broken down by remitted/unremitted status.
    """
    return WorkLogService.list_all_worklogs(
        session=session,
        remittance_status=remittanceStatus,
    )


@router.post(
    "/generate-remittances-for-all-users",
    response_model=GenerateRemittancesResponse,
    dependencies=[Depends(get_current_active_superuser)],
    summary="Generate remittances for all users",
    description="""
    Generates remittances for all users with outstanding (unremitted) work.
    
    **Key Features:**
    - Delta-based settlement: Only pays amounts not previously paid
    - Per-segment tracking: Each segment is marked as remitted
    - Dry-run mode: Preview without committing changes
    - Period filtering: Specify settlement period dates
    
    **Settlement Process:**
    1. Finds all unremitted time segments and adjustments
    2. Groups by worker
    3. Calculates gross (positive) and net (including deductions) amounts
    4. Creates remittance records
    5. Links segments/adjustments to their remittance
    6. Updates worklog running totals
    
    **Requires:** Superuser authentication
    """,
)
def generate_remittances_for_all_users(
    session: SessionDep,
    body: GenerateRemittancesRequest | None = None,
) -> Any:
    """
    Generate remittances for all eligible workers.
    
    Creates remittance records for workers with unremitted work,
    calculating amounts from active time segments and adjustments.
    
    Supports dry-run mode to preview without persisting.
    """
    request = body or GenerateRemittancesRequest()
    return WorkLogService.generate_remittances(
        session=session,
        request=request,
    )

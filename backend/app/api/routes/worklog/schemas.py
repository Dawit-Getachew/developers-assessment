"""
WorkLog Settlement System - Pydantic Schemas

Request/response models for API endpoints.
Designed for comprehensive validation and documentation.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.api.routes.worklog.models import (
    AdjustmentType,
    RemittanceStatus,
    SettlementStatus,
    TimeSegmentStatus,
)


# =============================================================================
# Nested Models for WorkLog
# =============================================================================


class TimeSegmentPublic(BaseModel):
    """Time segment within a worklog."""
    id: uuid.UUID
    start_time: datetime
    end_time: datetime
    status: TimeSegmentStatus
    settlement_status: SettlementStatus = SettlementStatus.UNREMITTED

    model_config = {"from_attributes": True}


class AdjustmentPublic(BaseModel):
    """Adjustment applied to a worklog."""
    id: uuid.UUID
    amount: Decimal
    reason: str
    type: AdjustmentType
    settlement_status: SettlementStatus = SettlementStatus.UNREMITTED

    model_config = {"from_attributes": True}


class WorkLogAmount(BaseModel):
    """Calculated amounts for a worklog."""
    remitted_amount: Decimal = Field(
        description="Amount already paid in previous remittances"
    )
    unremitted_amount: Decimal = Field(
        description="Amount not yet paid (eligible for next remittance)"
    )
    total_amount: Decimal = Field(
        description="Total calculated amount (remitted + unremitted)"
    )


# =============================================================================
# WorkLog Response Models
# =============================================================================


class WorkLogPublic(BaseModel):
    """
    Complete worklog representation for API responses.
    
    Includes nested segments, adjustments, and calculated amounts.
    """
    id: uuid.UUID
    task_id: uuid.UUID
    worker_id: uuid.UUID
    hourly_rate: Decimal
    remittance_id: uuid.UUID | None
    created_at: datetime
    time_segments: list[TimeSegmentPublic] = []
    adjustments: list[AdjustmentPublic] = []
    amounts: WorkLogAmount
    remittance_status: str = Field(
        description="REMITTED if fully paid, UNREMITTED if has unpaid amounts"
    )

    @computed_field
    def amount(self) -> Decimal:
        """Total calculated amount (compatibility field)."""
        return self.amounts.total_amount

    model_config = {"from_attributes": True}


class WorkLogsPublic(BaseModel):
    """Paginated list of worklogs."""
    data: list[WorkLogPublic]
    count: int


# =============================================================================
# Remittance Models
# =============================================================================


class RemittancePublic(BaseModel):
    """Remittance record for API responses."""
    id: uuid.UUID
    worker_id: uuid.UUID
    gross_amount: Decimal = Field(description="Total positive amounts")
    net_amount: Decimal = Field(description="Net after deductions")
    status: RemittanceStatus
    worklogs_count: int
    period_start: date | None = None
    period_end: date | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# Request Models
# =============================================================================


class GenerateRemittancesRequest(BaseModel):
    """
    Request body for generating remittances.
    
    All fields are optional with sensible defaults.
    """
    period_start: date | None = Field(
        default=None,
        description="Start of settlement period (defaults to first of current month)"
    )
    period_end: date | None = Field(
        default=None,
        description="End of settlement period (defaults to last of current month)"
    )
    dry_run: bool = Field(
        default=False,
        description="If true, preview remittances without persisting"
    )
    payout_status: RemittanceStatus | None = Field(
        default=None,
        description="Override payout status (defaults to COMPLETED)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "period_start": "2026-01-01",
                    "period_end": "2026-01-31",
                    "dry_run": False,
                }
            ]
        }
    }


# =============================================================================
# Response Models
# =============================================================================


class GenerateRemittancesResponse(BaseModel):
    """
    Response from remittance generation endpoint.
    
    Includes summary statistics and detailed remittance list.
    """
    remittances_created: int = Field(description="Number of remittances created")
    total_gross_amount: Decimal = Field(description="Sum of all gross amounts")
    total_net_amount: Decimal = Field(description="Sum of all net amounts")
    remittances: list[RemittancePublic]
    dry_run: bool = Field(description="Whether this was a preview run")
    period_start: date
    period_end: date

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "remittances_created": 2,
                    "total_gross_amount": "1500.00",
                    "total_net_amount": "1450.00",
                    "remittances": [],
                    "dry_run": False,
                    "period_start": "2026-01-01",
                    "period_end": "2026-01-31",
                }
            ]
        }
    }

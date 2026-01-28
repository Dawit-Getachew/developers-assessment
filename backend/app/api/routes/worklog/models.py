"""
WorkLog Settlement System - Database Models

Tables for tracking worker time, adjustments, and payment settlements.
Designed to handle:
- Work evolving after payment (new segments added)
- Retroactive adjustments (deductions applied to settled work)
- Settlement failures (tracking payout status)
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models import User


# =============================================================================
# Enums
# =============================================================================


class TimeSegmentStatus(str, Enum):
    """Status of a time segment within a worklog."""
    ACTIVE = "ACTIVE"       # Counted toward payment
    REMOVED = "REMOVED"     # Deleted/cancelled
    DISPUTED = "DISPUTED"   # Under review, not counted


class SettlementStatus(str, Enum):
    """Settlement status for individual segments/adjustments."""
    UNREMITTED = "UNREMITTED"  # Not yet paid
    REMITTED = "REMITTED"      # Included in a remittance


class AdjustmentType(str, Enum):
    """Type of adjustment applied to a worklog."""
    DEDUCTION = "DEDUCTION"   # Quality issue - negative amount
    BONUS = "BONUS"           # Extra payment - positive amount
    CORRECTION = "CORRECTION" # Error fix - can be positive or negative


class RemittanceStatus(str, Enum):
    """Status of a remittance payout attempt."""
    PENDING = "PENDING"       # Created, not yet processed
    PROCESSING = "PROCESSING" # Payment in progress
    COMPLETED = "COMPLETED"   # Successfully paid
    FAILED = "FAILED"         # Payment failed
    CANCELLED = "CANCELLED"   # Manually cancelled


# =============================================================================
# Database Models
# =============================================================================


class Task(SQLModel, table=True):
    """Billable task that workers log time against."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: Optional[str] = Field(default=None, max_length=1024)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    worklogs: list["WorkLog"] = Relationship(back_populates="task")


class Remittance(SQLModel, table=True):
    """
    Single payout to a worker for a settlement period.
    
    Tracks both gross and net amounts to handle adjustments,
    and includes failure tracking for retry scenarios.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worker_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    
    # Amount tracking
    gross_amount: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    net_amount: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    
    # Status and lifecycle
    status: RemittanceStatus = Field(default=RemittanceStatus.PENDING)
    failure_reason: Optional[str] = Field(default=None, max_length=500)
    
    # Period tracking
    period_start: Optional[datetime] = Field(default=None)
    period_end: Optional[datetime] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = Field(default=None)
    
    # Relationships
    worklogs: list["WorkLog"] = Relationship(back_populates="remittance")


class WorkLog(SQLModel, table=True):
    """
    Container for work done by a worker on a task.
    
    Links to multiple time segments and adjustments.
    Tracks total remitted amount for delta calculations.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    task_id: uuid.UUID = Field(foreign_key="task.id", nullable=False, index=True)
    worker_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, index=True)
    hourly_rate: Decimal = Field(default=Decimal("0"), max_digits=10, decimal_places=2)
    
    # Delta tracking: how much has already been paid for this worklog
    total_remitted_amount: Decimal = Field(
        default=Decimal("0"), max_digits=12, decimal_places=2,
        description="Running total of amounts already settled"
    )
    
    # Link to current/last remittance (nullable until settled)
    remittance_id: Optional[uuid.UUID] = Field(default=None, foreign_key="remittance.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    task: Task = Relationship(back_populates="worklogs")
    remittance: Optional[Remittance] = Relationship(back_populates="worklogs")
    time_segments: list["TimeSegment"] = Relationship(
        back_populates="worklog", cascade_delete=True
    )
    adjustments: list["Adjustment"] = Relationship(
        back_populates="worklog", cascade_delete=True
    )


class TimeSegment(SQLModel, table=True):
    """
    Individual time entry within a worklog.
    
    Tracks settlement status separately to support retroactive work
    being added after initial settlement.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worklog_id: uuid.UUID = Field(foreign_key="worklog.id", nullable=False, index=True)
    
    # Time tracking
    start_time: datetime
    end_time: datetime
    
    # Status tracking
    status: TimeSegmentStatus = Field(default=TimeSegmentStatus.ACTIVE)
    settlement_status: SettlementStatus = Field(default=SettlementStatus.UNREMITTED)
    
    # Optional: link to the remittance that settled this segment
    remittance_id: Optional[uuid.UUID] = Field(default=None, foreign_key="remittance.id")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    worklog: WorkLog = Relationship(back_populates="time_segments")


class Adjustment(SQLModel, table=True):
    """
    Quality deduction or bonus applied to a worklog.
    
    Supports retroactive adjustments by tracking settlement status
    independently of the parent worklog.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    worklog_id: uuid.UUID = Field(foreign_key="worklog.id", nullable=False, index=True)
    
    # Amount can be negative (deduction) or positive (bonus)
    amount: Decimal = Field(max_digits=10, decimal_places=2)
    reason: str = Field(max_length=500)
    type: AdjustmentType
    
    # Settlement tracking for retroactive adjustments
    settlement_status: SettlementStatus = Field(default=SettlementStatus.UNREMITTED)
    remittance_id: Optional[uuid.UUID] = Field(default=None, foreign_key="remittance.id")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    worklog: WorkLog = Relationship(back_populates="adjustments")

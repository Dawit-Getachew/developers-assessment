"""
WorkLog Settlement System - Service Layer

Business logic for worklog listing and remittance generation.
Designed for correctness, auditability, and handling edge cases.
"""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.routes.worklog.models import (
    Adjustment,
    Remittance,
    RemittanceStatus,
    SettlementStatus,
    TimeSegment,
    TimeSegmentStatus,
    WorkLog,
)
from app.api.routes.worklog.schemas import (
    GenerateRemittancesRequest,
    GenerateRemittancesResponse,
    RemittancePublic,
    WorkLogAmount,
    WorkLogPublic,
    WorkLogsPublic,
)


class WorkLogService:
    """
    Service class for WorkLog settlement operations.
    
    Key features:
    - Delta-based settlement (only pays unpaid amounts)
    - Per-segment/adjustment settlement tracking
    - Dry-run mode for previewing settlements
    - Period validation and filtering
    - Comprehensive error handling
    """

    # =========================================================================
    # Calculation Helpers
    # =========================================================================

    @staticmethod
    def _calculate_segment_amount(
        segment: TimeSegment, hourly_rate: Decimal
    ) -> Decimal:
        """Calculate amount for a single time segment."""
        if segment.status != TimeSegmentStatus.ACTIVE:
            return Decimal("0")
        
        duration = segment.end_time - segment.start_time
        if duration.total_seconds() < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Segment {segment.id} has negative duration"
            )
        
        hours = Decimal(str(duration.total_seconds())) / Decimal("3600")
        amount = (hours * hourly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return amount

    @staticmethod
    def _calculate_worklog_amounts(
        worklog: WorkLog,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate amounts for a worklog.
        
        Returns:
            Tuple of (remitted_amount, unremitted_amount, total_amount)
        """
        remitted = Decimal("0")
        unremitted = Decimal("0")
        
        # Calculate from time segments
        for segment in worklog.time_segments:
            if segment.status != TimeSegmentStatus.ACTIVE:
                continue
            
            amount = WorkLogService._calculate_segment_amount(
                segment, worklog.hourly_rate
            )
            
            if segment.settlement_status == SettlementStatus.REMITTED:
                remitted += amount
            else:
                unremitted += amount
        
        # Add adjustments
        for adj in worklog.adjustments:
            if adj.settlement_status == SettlementStatus.REMITTED:
                remitted += adj.amount
            else:
                unremitted += adj.amount
        
        total = remitted + unremitted
        return remitted, unremitted, total

    @staticmethod
    def _resolve_period(
        period_start: date | None, period_end: date | None
    ) -> tuple[date, date]:
        """
        Resolve settlement period dates with validation.
        
        Defaults to current month if not specified.
        """
        today = date.today()
        
        if period_start is None:
            period_start = today.replace(day=1)
        
        if period_end is None:
            # Default to end of current month
            next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
            period_end = next_month - timedelta(days=1)
        
        if period_end < period_start:
            raise HTTPException(
                status_code=400,
                detail="period_end must be on or after period_start"
            )
        
        return period_start, period_end

    # =========================================================================
    # Public API Methods
    # =========================================================================

    @staticmethod
    def list_all_worklogs(
        session: Session,
        remittance_status: str | None = None,
    ) -> WorkLogsPublic:
        """
        List all worklogs with filtering and calculated amounts.
        
        Args:
            session: Database session
            remittance_status: Filter by REMITTED or UNREMITTED
        
        Returns:
            WorkLogsPublic with list of worklogs and counts
        """
        # Validate filter parameter
        valid_statuses = {"REMITTED", "UNREMITTED", None}
        if remittance_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"remittanceStatus must be REMITTED or UNREMITTED"
            )
        
        # Fetch all worklogs with relationships eager-loaded
        worklogs = session.exec(select(WorkLog)).all()
        
        result: list[WorkLogPublic] = []
        
        for wl in worklogs:
            remitted, unremitted, total = WorkLogService._calculate_worklog_amounts(wl)
            
            # Determine worklog's remittance status based on amounts
            if unremitted > 0 or total == 0:
                wl_status = "UNREMITTED"
            else:
                wl_status = "REMITTED"
            
            # Apply filter
            if remittance_status and wl_status != remittance_status:
                continue
            
            # Build response object
            time_segments_data = [
                {
                    "id": seg.id,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "status": seg.status,
                    "settlement_status": seg.settlement_status,
                }
                for seg in wl.time_segments
            ]
            
            adjustments_data = [
                {
                    "id": adj.id,
                    "amount": adj.amount,
                    "reason": adj.reason,
                    "type": adj.type,
                    "settlement_status": adj.settlement_status,
                }
                for adj in wl.adjustments
            ]
            
            result.append(WorkLogPublic(
                id=wl.id,
                task_id=wl.task_id,
                worker_id=wl.worker_id,
                hourly_rate=wl.hourly_rate,
                remittance_id=wl.remittance_id,
                created_at=wl.created_at,
                time_segments=time_segments_data,
                adjustments=adjustments_data,
                amounts=WorkLogAmount(
                    remitted_amount=remitted,
                    unremitted_amount=unremitted,
                    total_amount=total,
                ),
                remittance_status=wl_status,
            ))
        
        return WorkLogsPublic(data=result, count=len(result))

    @staticmethod
    def generate_remittances(
        session: Session,
        request: GenerateRemittancesRequest,
    ) -> GenerateRemittancesResponse:
        """
        Generate remittances for all users with outstanding payments.
        
        Implements delta-based settlement:
        - Only settles unremitted segments/adjustments
        - Links each segment/adjustment to its remittance
        - Supports dry-run mode for preview
        - Handles negative totals gracefully
        
        Args:
            session: Database session
            request: Configuration for remittance generation
        
        Returns:
            GenerateRemittancesResponse with created remittances
        """
        # Resolve period
        period_start, period_end = WorkLogService._resolve_period(
            request.period_start, request.period_end
        )
        
        # Convert to datetime for comparison with timestamps
        period_start_dt = datetime.combine(period_start, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        period_end_dt = datetime.combine(period_end, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )
        
        # Fetch unremitted segments
        unremitted_segments = session.exec(
            select(TimeSegment).where(
                TimeSegment.status == TimeSegmentStatus.ACTIVE,
                TimeSegment.settlement_status == SettlementStatus.UNREMITTED,
            )
        ).all()
        
        # Fetch unremitted adjustments
        unremitted_adjustments = session.exec(
            select(Adjustment).where(
                Adjustment.settlement_status == SettlementStatus.UNREMITTED
            )
        ).all()
        
        # Group by worker
        worker_segments: dict[uuid.UUID, list[tuple[TimeSegment, WorkLog]]] = defaultdict(list)
        worker_adjustments: dict[uuid.UUID, list[tuple[Adjustment, WorkLog]]] = defaultdict(list)
        worklog_cache: dict[uuid.UUID, WorkLog] = {}
        
        for seg in unremitted_segments:
            if seg.worklog_id not in worklog_cache:
                wl = session.exec(
                    select(WorkLog).where(WorkLog.id == seg.worklog_id)
                ).first()
                if wl:
                    worklog_cache[seg.worklog_id] = wl
            
            wl = worklog_cache.get(seg.worklog_id)
            if wl:
                worker_segments[wl.worker_id].append((seg, wl))
        
        for adj in unremitted_adjustments:
            if adj.worklog_id not in worklog_cache:
                wl = session.exec(
                    select(WorkLog).where(WorkLog.id == adj.worklog_id)
                ).first()
                if wl:
                    worklog_cache[adj.worklog_id] = wl
            
            wl = worklog_cache.get(adj.worklog_id)
            if wl:
                worker_adjustments[wl.worker_id].append((adj, wl))
        
        # Get all unique worker IDs
        all_worker_ids = set(worker_segments.keys()) | set(worker_adjustments.keys())
        
        remittances_created: list[RemittancePublic] = []
        total_gross = Decimal("0")
        total_net = Decimal("0")
        now = datetime.now(timezone.utc)
        
        for worker_id in all_worker_ids:
            segments = worker_segments.get(worker_id, [])
            adjustments = worker_adjustments.get(worker_id, [])
            
            # Calculate gross (positive amounts only) and net
            gross_amount = Decimal("0")
            net_amount = Decimal("0")
            worklog_ids: set[uuid.UUID] = set()
            
            for seg, wl in segments:
                amount = WorkLogService._calculate_segment_amount(seg, wl.hourly_rate)
                net_amount += amount
                if amount > 0:
                    gross_amount += amount
                worklog_ids.add(wl.id)
            
            for adj, wl in adjustments:
                net_amount += adj.amount
                if adj.amount > 0:
                    gross_amount += adj.amount
                worklog_ids.add(wl.id)
            
            # Skip if nothing to settle
            if gross_amount == 0 and net_amount == 0:
                continue
            
            # Determine status based on request or defaults
            status = request.payout_status or RemittanceStatus.COMPLETED
            failure_reason = None
            if status in {RemittanceStatus.FAILED, RemittanceStatus.CANCELLED}:
                failure_reason = f"Payout marked as {status.value} by request"
            
            # Create remittance
            remittance = Remittance(
                worker_id=worker_id,
                gross_amount=gross_amount.quantize(Decimal("0.01")),
                net_amount=net_amount.quantize(Decimal("0.01")),
                status=status,
                failure_reason=failure_reason,
                period_start=period_start_dt,
                period_end=period_end_dt,
                processed_at=now if status == RemittanceStatus.COMPLETED else None,
            )
            
            if request.dry_run:
                # In dry-run mode, don't persist anything
                remittances_created.append(RemittancePublic(
                    id=uuid.uuid4(),  # Fake ID for preview
                    worker_id=worker_id,
                    gross_amount=remittance.gross_amount,
                    net_amount=remittance.net_amount,
                    status=remittance.status,
                    worklogs_count=len(worklog_ids),
                    period_start=period_start,
                    period_end=period_end,
                ))
                total_gross += gross_amount
                total_net += net_amount
                continue
            
            # Persist remittance
            session.add(remittance)
            session.flush()  # Get the ID
            
            # Mark segments as remitted (only if status is successful)
            if status == RemittanceStatus.COMPLETED:
                for seg, wl in segments:
                    seg.settlement_status = SettlementStatus.REMITTED
                    seg.remittance_id = remittance.id
                    session.add(seg)
                    
                    # Update worklog's total remitted amount
                    amount = WorkLogService._calculate_segment_amount(seg, wl.hourly_rate)
                    wl.total_remitted_amount += amount
                    wl.remittance_id = remittance.id
                    session.add(wl)
                
                for adj, wl in adjustments:
                    adj.settlement_status = SettlementStatus.REMITTED
                    adj.remittance_id = remittance.id
                    session.add(adj)
                    
                    # Update worklog's total remitted amount
                    wl.total_remitted_amount += adj.amount
                    session.add(wl)
            
            remittances_created.append(RemittancePublic(
                id=remittance.id,
                worker_id=remittance.worker_id,
                gross_amount=remittance.gross_amount,
                net_amount=remittance.net_amount,
                status=remittance.status,
                worklogs_count=len(worklog_ids),
                period_start=period_start,
                period_end=period_end,
            ))
            
            total_gross += gross_amount
            total_net += net_amount
        
        if not request.dry_run:
            session.commit()
        
        return GenerateRemittancesResponse(
            remittances_created=len(remittances_created),
            total_gross_amount=total_gross.quantize(Decimal("0.01")),
            total_net_amount=total_net.quantize(Decimal("0.01")),
            remittances=remittances_created,
            dry_run=request.dry_run,
            period_start=period_start,
            period_end=period_end,
        )

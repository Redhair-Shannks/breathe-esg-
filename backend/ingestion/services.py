from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    ActivityRecord,
    AuditEvent,
    EmissionEstimate,
    EmissionFactor,
    IngestionBatch,
    RawSourceRecord,
    ReviewDecision,
    SourceSystem,
    Tenant,
    ValidationIssue,
)
from .parsers import PARSERS, UploadFormatError, has_blocking_issue, infer_source_kind, read_csv_rows, stable_row_hash


def get_demo_user(request):
    if request and request.user and request.user.is_authenticated:
        return request.user
    return None


def get_tenant(slug=None):
    if slug:
        return Tenant.objects.get(slug=slug)
    return Tenant.objects.order_by("id").first()


def create_issue(batch, raw_record, activity, parser_issue):
    return ValidationIssue.objects.create(
        tenant=batch.tenant,
        batch=batch,
        raw_record=raw_record,
        activity=activity,
        severity=parser_issue.severity,
        code=parser_issue.code,
        field=parser_issue.field,
        message=parser_issue.message,
    )


def matching_factor(activity):
    if not activity.normalized_unit:
        return None
    geography = activity.facility.grid_region if activity.facility else ""
    filters = {
        "activity_kind": activity.activity_kind,
        "scope": activity.scope,
        "factor_unit": activity.normalized_unit,
    }
    candidates = EmissionFactor.objects.filter(Q(tenant=activity.tenant) | Q(tenant__isnull=True), **filters)
    if geography:
        factor = candidates.filter(geography=geography).first()
        if factor:
            return factor
    return candidates.filter(geography="").first() or candidates.first()


def calculate_emissions(activity):
    factor = matching_factor(activity)
    if not factor or activity.normalized_quantity is None or activity.normalized_quantity < 0:
        EmissionEstimate.objects.update_or_create(
            activity=activity,
            defaults={
                "factor": factor,
                "co2e_kg": None,
                "calculation_note": "No matching factor or normalized quantity.",
            },
        )
        return None
    co2e_kg = activity.normalized_quantity * factor.kg_co2e_per_unit
    estimate, _ = EmissionEstimate.objects.update_or_create(
        activity=activity,
        defaults={
            "factor": factor,
            "co2e_kg": co2e_kg.quantize(Decimal("0.0001")),
            "calculation_note": f"{activity.normalized_quantity} {activity.normalized_unit} * {factor.kg_co2e_per_unit} kgCO2e/{factor.factor_unit}",
        },
    )
    return estimate


def add_post_parse_checks(activity):
    issues = []
    if activity.activity_kind == ActivityRecord.ActivityKind.ELECTRICITY:
        meter_key = activity.metadata.get("utility_meter_key") or activity.metadata.get("meter_id")
        if meter_key and activity.period_start and activity.period_end:
            overlaps = ActivityRecord.objects.filter(
                tenant=activity.tenant,
                activity_kind=ActivityRecord.ActivityKind.ELECTRICITY,
                metadata__utility_meter_key=meter_key,
                period_start__lte=activity.period_end,
                period_end__gte=activity.period_start,
            ).exclude(id=activity.id)
            if overlaps.exists():
                issues.append(
                    ValidationIssue.objects.create(
                        tenant=activity.tenant,
                        batch=activity.batch,
                        raw_record=activity.raw_record,
                        activity=activity,
                        severity=ValidationIssue.Severity.WARNING,
                        code="OVERLAPPING_BILLING_PERIOD",
                        field="period",
                        message=f"Meter {meter_key} has another row overlapping this billing period.",
                    )
                )
            previous = (
                ActivityRecord.objects.filter(
                    tenant=activity.tenant,
                    activity_kind=ActivityRecord.ActivityKind.ELECTRICITY,
                    metadata__utility_meter_key=meter_key,
                    period_end__lt=activity.period_start,
                    normalized_quantity__isnull=False,
                )
                .exclude(id=activity.id)
                .order_by("-period_end")
                .first()
            )
            if (
                previous
                and previous.normalized_quantity
                and activity.normalized_quantity
                and activity.normalized_quantity > previous.normalized_quantity * Decimal("3")
            ):
                issues.append(
                    ValidationIssue.objects.create(
                        tenant=activity.tenant,
                        batch=activity.batch,
                        raw_record=activity.raw_record,
                        activity=activity,
                        severity=ValidationIssue.Severity.WARNING,
                        code="USAGE_SPIKE",
                        field="quantity",
                        message="Usage is more than 3x the previous billing period for the same meter.",
                    )
                )
    return issues


@transaction.atomic
def process_upload(*, tenant, source_kind, uploaded_file, file_name, user=None):
    source_system = SourceSystem.objects.filter(tenant=tenant, kind=source_kind, is_active=True).first()
    if not source_system:
        source_system = SourceSystem.objects.create(
            tenant=tenant,
            kind=source_kind,
            name=f"{source_kind.title()} upload",
            description="Created automatically for uploaded prototype data.",
        )
    batch = IngestionBatch.objects.create(
        tenant=tenant,
        source_system=source_system,
        source_kind=source_kind,
        file_name=file_name,
        created_by=user,
    )
    parser = PARSERS[source_kind]
    rows = read_csv_rows(uploaded_file)
    inferred_source_kind = infer_source_kind(rows)
    if inferred_source_kind and inferred_source_kind != source_kind:
        raise UploadFormatError(
            f"The selected source is {source_kind}, but the file headers look like {inferred_source_kind}. "
            f"Select {inferred_source_kind} and upload the file again."
        )
    batch.row_count = len(rows)
    batch.save(update_fields=["row_count"])

    for index, row in enumerate(rows, start=1):
        row_hash = stable_row_hash(row)
        raw_record = RawSourceRecord.objects.create(
            tenant=tenant,
            batch=batch,
            source_system=source_system,
            row_number=index,
            source_external_id=row.get("Document Number") or row.get("Entry ID") or row.get("Meter ID") or "",
            row_hash=row_hash,
            payload=row,
        )
        parsed = parser(tenant, row)
        review_status = (
            ActivityRecord.ReviewStatus.BLOCKED
            if has_blocking_issue(parsed.issues)
            else ActivityRecord.ReviewStatus.NEEDS_REVIEW
        )
        activity = ActivityRecord.objects.create(
            tenant=tenant,
            batch=batch,
            raw_record=raw_record,
            source_system=source_system,
            source_hash=row_hash,
            review_status=review_status,
            **parsed.data,
        )
        for issue in parsed.issues:
            create_issue(batch, raw_record, activity, issue)
        add_post_parse_checks(activity)
        estimate = calculate_emissions(activity)
        if not estimate or estimate.co2e_kg is None:
            ValidationIssue.objects.create(
                tenant=tenant,
                batch=batch,
                raw_record=raw_record,
                activity=activity,
                severity=ValidationIssue.Severity.WARNING,
                code="NO_EMISSION_ESTIMATE",
                field="emission_factor",
                message="No emission estimate could be calculated from the available normalized quantity and factor library.",
            )
        AuditEvent.objects.create(
            tenant=tenant,
            batch=batch,
            activity=activity,
            actor=user,
            event_type="activity.ingested",
            after={"activity_id": activity.id, "row_hash": row_hash, "review_status": review_status},
            note="Created from source upload.",
        )

    error_rows = ActivityRecord.objects.filter(
        batch=batch,
        validation_issues__severity=ValidationIssue.Severity.ERROR,
        validation_issues__status=ValidationIssue.Status.OPEN,
    ).distinct()
    warning_rows = ActivityRecord.objects.filter(
        batch=batch,
        validation_issues__severity=ValidationIssue.Severity.WARNING,
        validation_issues__status=ValidationIssue.Status.OPEN,
    ).distinct()
    batch.imported_count = ActivityRecord.objects.filter(batch=batch).count()
    batch.failed_count = error_rows.count()
    batch.warning_count = warning_rows.count()
    batch.status = IngestionBatch.Status.PROCESSED
    batch.completed_at = timezone.now()
    batch.save()
    AuditEvent.objects.create(
        tenant=tenant,
        batch=batch,
        actor=user,
        event_type="batch.processed",
        after={
            "row_count": batch.row_count,
            "imported_count": batch.imported_count,
            "failed_count": batch.failed_count,
            "warning_count": batch.warning_count,
        },
    )
    return batch


def approve_activity(activity, user=None, note=""):
    if activity.is_locked:
        raise ValueError("Activity is already locked.")
    if activity.review_status == ActivityRecord.ReviewStatus.REJECTED:
        raise ValueError("Rejected activity cannot be approved without reopening it.")
    blocking = activity.validation_issues.filter(
        severity=ValidationIssue.Severity.ERROR,
        status=ValidationIssue.Status.OPEN,
    ).exists()
    if blocking:
        raise ValueError("Resolve blocking validation issues before approval.")
    before = {
        "review_status": activity.review_status,
        "locked_at": str(activity.locked_at) if activity.locked_at else None,
    }
    activity.review_status = ActivityRecord.ReviewStatus.LOCKED
    activity.locked_at = timezone.now()
    activity.approved_by = user
    activity.save(update_fields=["review_status", "locked_at", "approved_by", "updated_at"])
    ReviewDecision.objects.create(
        tenant=activity.tenant,
        activity=activity,
        decision=ReviewDecision.Decision.APPROVED,
        decided_by=user,
        note=note,
    )
    AuditEvent.objects.create(
        tenant=activity.tenant,
        activity=activity,
        actor=user,
        event_type="activity.approved_locked",
        before=before,
        after={"review_status": activity.review_status, "locked_at": str(activity.locked_at)},
        note=note,
    )
    return activity


def reject_activity(activity, user=None, note=""):
    if activity.is_locked:
        raise ValueError("Locked activity cannot be rejected.")
    if activity.review_status == ActivityRecord.ReviewStatus.REJECTED:
        raise ValueError("Activity is already rejected.")
    before = {"review_status": activity.review_status}
    activity.review_status = ActivityRecord.ReviewStatus.REJECTED
    activity.save(update_fields=["review_status", "updated_at"])
    ReviewDecision.objects.create(
        tenant=activity.tenant,
        activity=activity,
        decision=ReviewDecision.Decision.REJECTED,
        decided_by=user,
        note=note,
    )
    AuditEvent.objects.create(
        tenant=activity.tenant,
        activity=activity,
        actor=user,
        event_type="activity.rejected",
        before=before,
        after={"review_status": activity.review_status},
        note=note,
    )
    return activity


def reopen_activity(activity, user=None, note=""):
    if not activity.is_terminal:
        raise ValueError("Only locked or rejected activities can be reopened.")
    if not note:
        raise ValueError("A reopen note is required.")
    before = {
        "review_status": activity.review_status,
        "locked_at": str(activity.locked_at) if activity.locked_at else None,
        "approved_by_id": activity.approved_by_id,
    }
    activity.review_status = ActivityRecord.ReviewStatus.NEEDS_REVIEW
    activity.locked_at = None
    activity.approved_by = None
    activity.save(update_fields=["review_status", "locked_at", "approved_by", "updated_at"])
    ReviewDecision.objects.create(
        tenant=activity.tenant,
        activity=activity,
        decision=ReviewDecision.Decision.NEEDS_INFO,
        decided_by=user,
        note=note,
    )
    AuditEvent.objects.create(
        tenant=activity.tenant,
        activity=activity,
        actor=user,
        event_type="activity.reopened",
        before=before,
        after={"review_status": activity.review_status, "locked_at": None, "approved_by_id": None},
        note=note,
    )
    return activity


def update_activity(activity, changes, user=None, note=""):
    if activity.is_terminal:
        raise ValueError("Locked or rejected activity cannot be edited.")
    editable_fields = {
        "facility",
        "activity_date",
        "period_start",
        "period_end",
        "supplier",
        "category",
        "description",
        "normalized_quantity",
        "normalized_unit",
        "amount",
        "currency",
        "origin",
        "destination",
    }
    before = {field: str(getattr(activity, field)) for field in editable_fields if field in changes}
    for field, value in changes.items():
        if field in editable_fields:
            setattr(activity, field, value)
    activity.edited_from_raw = True
    activity.save()
    calculate_emissions(activity)
    AuditEvent.objects.create(
        tenant=activity.tenant,
        activity=activity,
        actor=user,
        event_type="activity.edited",
        before=before,
        after={field: str(getattr(activity, field)) for field in before},
        note=note,
    )
    return activity


def dashboard_summary(tenant):
    activities = ActivityRecord.objects.filter(tenant=tenant)
    estimates = EmissionEstimate.objects.filter(activity__tenant=tenant, co2e_kg__isnull=False)
    by_scope = (
        estimates.values("activity__scope")
        .annotate(total_kg=Sum("co2e_kg"), rows=Count("id"))
        .order_by("activity__scope")
    )
    by_source = (
        activities.values("source_system__kind")
        .annotate(rows=Count("id"))
        .order_by("source_system__kind")
    )
    issue_counts = ValidationIssue.objects.filter(tenant=tenant, status=ValidationIssue.Status.OPEN).aggregate(
        errors=Count("id", filter=Q(severity=ValidationIssue.Severity.ERROR)),
        warnings=Count("id", filter=Q(severity=ValidationIssue.Severity.WARNING)),
    )
    status_counts = activities.values("review_status").annotate(rows=Count("id"))
    return {
        "activity_count": activities.count(),
        "needs_review": activities.filter(review_status=ActivityRecord.ReviewStatus.NEEDS_REVIEW).count(),
        "blocked": activities.filter(review_status=ActivityRecord.ReviewStatus.BLOCKED).count(),
        "locked": activities.filter(review_status=ActivityRecord.ReviewStatus.LOCKED).count(),
        "rejected": activities.filter(review_status=ActivityRecord.ReviewStatus.REJECTED).count(),
        "open_errors": issue_counts["errors"] or 0,
        "open_warnings": issue_counts["warnings"] or 0,
        "estimated_kg_co2e": estimates.aggregate(total=Sum("co2e_kg"))["total"] or Decimal("0"),
        "by_scope": list(by_scope),
        "by_source": list(by_source),
        "status_counts": list(status_counts),
    }

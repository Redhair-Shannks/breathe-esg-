from django.conf import settings
from django.db import models
from django.utils import timezone


class Tenant(models.Model):
    name = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        ANALYST = "ANALYST", "Analyst"
        AUDITOR = "AUDITOR", "Auditor"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        unique_together = [("user", "tenant")]

    def __str__(self):
        return f"{self.user} / {self.tenant} / {self.role}"


class Facility(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="facilities")
    name = models.CharField(max_length=180)
    code = models.CharField(max_length=80)
    city = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=2, default="US")
    grid_region = models.CharField(max_length=40, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("tenant", "code")]
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SourceSystem(models.Model):
    class Kind(models.TextChoices):
        SAP = "SAP", "SAP fuel/procurement"
        UTILITY = "UTILITY", "Utility electricity"
        TRAVEL = "TRAVEL", "Corporate travel"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="source_systems")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("tenant", "kind", "name")]
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.tenant.slug}:{self.kind}:{self.name}"


class ReferenceMapping(models.Model):
    class MappingType(models.TextChoices):
        PLANT_CODE = "PLANT_CODE", "SAP plant code"
        MATERIAL_CODE = "MATERIAL_CODE", "SAP material code"
        METER_ID = "METER_ID", "Utility meter id"
        EXPENSE_TYPE = "EXPENSE_TYPE", "Travel expense type"
        AIRPORT_CODE = "AIRPORT_CODE", "Airport code"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="reference_mappings")
    mapping_type = models.CharField(max_length=40, choices=MappingType.choices)
    source_value = models.CharField(max_length=160)
    normalized_code = models.CharField(max_length=160)
    display_name = models.CharField(max_length=220)
    facility = models.ForeignKey(Facility, null=True, blank=True, on_delete=models.SET_NULL)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "mapping_type", "source_value")]
        indexes = [
            models.Index(fields=["tenant", "mapping_type", "source_value"]),
        ]
        ordering = ["mapping_type", "source_value"]

    def __str__(self):
        return f"{self.mapping_type}:{self.source_value}->{self.normalized_code}"


class IngestionBatch(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="batches")
    source_system = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="batches")
    source_kind = models.CharField(max_length=20, choices=SourceSystem.Kind.choices)
    file_name = models.CharField(max_length=255)
    parser_version = models.CharField(max_length=40, default="2026-05-v1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    row_count = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_batches",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source_kind} {self.file_name} ({self.status})"


class RawSourceRecord(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="raw_records")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    source_system = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="raw_records")
    row_number = models.PositiveIntegerField()
    source_external_id = models.CharField(max_length=220, blank=True)
    row_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "source_system", "row_hash"]),
            models.Index(fields=["batch", "row_number"]),
        ]
        ordering = ["batch_id", "row_number"]

    def __str__(self):
        return f"{self.batch_id}:{self.row_number}"


class ActivityRecord(models.Model):
    class ActivityKind(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        PROCUREMENT = "PROCUREMENT", "Procurement"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        FLIGHT = "FLIGHT", "Flight"
        HOTEL = "HOTEL", "Hotel"
        GROUND = "GROUND", "Ground transport"

    class Scope(models.TextChoices):
        SCOPE_1 = "SCOPE_1", "Scope 1"
        SCOPE_2 = "SCOPE_2", "Scope 2"
        SCOPE_3 = "SCOPE_3", "Scope 3"

    class ReviewStatus(models.TextChoices):
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
        BLOCKED = "BLOCKED", "Blocked"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        LOCKED = "LOCKED", "Locked"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="activities")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="activities")
    raw_record = models.OneToOneField(
        RawSourceRecord,
        on_delete=models.CASCADE,
        related_name="activity",
        null=True,
        blank=True,
    )
    source_system = models.ForeignKey(SourceSystem, on_delete=models.PROTECT, related_name="activities")
    external_id = models.CharField(max_length=220, blank=True)
    activity_kind = models.CharField(max_length=30, choices=ActivityKind.choices)
    scope = models.CharField(max_length=20, choices=Scope.choices)
    facility = models.ForeignKey(Facility, null=True, blank=True, on_delete=models.SET_NULL)
    activity_date = models.DateField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=220, blank=True)
    category = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    original_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    original_unit = models.CharField(max_length=40, blank=True)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    normalized_unit = models.CharField(max_length=40, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    origin = models.CharField(max_length=20, blank=True)
    destination = models.CharField(max_length=20, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NEEDS_REVIEW,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_activities",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    edited_from_raw = models.BooleanField(default=False)
    source_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "review_status"]),
            models.Index(fields=["tenant", "scope"]),
            models.Index(fields=["tenant", "activity_kind"]),
            models.Index(fields=["tenant", "activity_date"]),
        ]
        ordering = ["-activity_date", "-id"]

    @property
    def is_locked(self):
        return self.review_status == self.ReviewStatus.LOCKED or self.locked_at is not None

    def __str__(self):
        return f"{self.activity_kind} {self.normalized_quantity} {self.normalized_unit}"


class ValidationIssue(models.Model):
    class Severity(models.TextChoices):
        ERROR = "ERROR", "Error"
        WARNING = "WARNING", "Warning"
        INFO = "INFO", "Info"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="validation_issues")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="validation_issues")
    raw_record = models.ForeignKey(
        RawSourceRecord,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="validation_issues",
    )
    activity = models.ForeignKey(
        ActivityRecord,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="validation_issues",
    )
    severity = models.CharField(max_length=20, choices=Severity.choices)
    code = models.CharField(max_length=80)
    field = models.CharField(max_length=120, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "severity", "status"]),
            models.Index(fields=["batch", "severity"]),
        ]
        ordering = ["severity", "code", "id"]

    def __str__(self):
        return f"{self.severity}:{self.code}"


class EmissionFactor(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="emission_factors",
    )
    activity_kind = models.CharField(max_length=30, choices=ActivityRecord.ActivityKind.choices)
    scope = models.CharField(max_length=20, choices=ActivityRecord.Scope.choices)
    label = models.CharField(max_length=220)
    factor_unit = models.CharField(max_length=40)
    kg_co2e_per_unit = models.DecimalField(max_digits=18, decimal_places=8)
    geography = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=220)
    source_url = models.URLField(blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["activity_kind", "geography", "label"]

    def __str__(self):
        return f"{self.label} ({self.kg_co2e_per_unit}/{self.factor_unit})"


class EmissionEstimate(models.Model):
    activity = models.OneToOneField(
        ActivityRecord,
        on_delete=models.CASCADE,
        related_name="emission_estimate",
    )
    factor = models.ForeignKey(EmissionFactor, null=True, blank=True, on_delete=models.SET_NULL)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    calculation_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.activity_id}: {self.co2e_kg} kgCO2e"


class ReviewDecision(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        NEEDS_INFO = "NEEDS_INFO", "Needs info"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="review_decisions")
    activity = models.ForeignKey(ActivityRecord, on_delete=models.CASCADE, related_name="review_decisions")
    decision = models.CharField(max_length=20, choices=Decision.choices)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AuditEvent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="audit_events")
    activity = models.ForeignKey(
        ActivityRecord,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    batch = models.ForeignKey(
        IngestionBatch,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="audit_events",
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=80)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["tenant", "event_type"]),
            models.Index(fields=["activity", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"


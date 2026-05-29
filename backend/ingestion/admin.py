from django.contrib import admin

from .models import (
    ActivityRecord,
    AuditEvent,
    EmissionEstimate,
    EmissionFactor,
    Facility,
    IngestionBatch,
    RawSourceRecord,
    ReferenceMapping,
    ReviewDecision,
    SourceSystem,
    Tenant,
    UserMembership,
    ValidationIssue,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("tenant", "code", "name", "city", "country", "grid_region")
    list_filter = ("tenant", "country", "grid_region")
    search_fields = ("code", "name", "city")


@admin.register(SourceSystem)
class SourceSystemAdmin(admin.ModelAdmin):
    list_display = ("tenant", "kind", "name", "is_active")
    list_filter = ("tenant", "kind", "is_active")


@admin.register(ReferenceMapping)
class ReferenceMappingAdmin(admin.ModelAdmin):
    list_display = ("tenant", "mapping_type", "source_value", "normalized_code", "display_name", "facility")
    list_filter = ("tenant", "mapping_type")
    search_fields = ("source_value", "normalized_code", "display_name")


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ("tenant", "source_kind", "file_name", "status", "row_count", "failed_count", "warning_count", "started_at")
    list_filter = ("tenant", "source_kind", "status")


@admin.register(RawSourceRecord)
class RawSourceRecordAdmin(admin.ModelAdmin):
    list_display = ("tenant", "batch", "row_number", "source_external_id", "row_hash")
    list_filter = ("tenant", "source_system")
    search_fields = ("source_external_id", "row_hash")


@admin.register(ActivityRecord)
class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ("tenant", "activity_kind", "scope", "facility", "activity_date", "normalized_quantity", "normalized_unit", "review_status")
    list_filter = ("tenant", "activity_kind", "scope", "review_status")
    search_fields = ("external_id", "description", "supplier", "category")


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("tenant", "batch", "severity", "code", "field", "status")
    list_filter = ("tenant", "severity", "status", "code")


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ("activity_kind", "scope", "label", "geography", "factor_unit", "kg_co2e_per_unit", "source")
    list_filter = ("activity_kind", "scope", "geography")


admin.site.register(EmissionEstimate)
admin.site.register(ReviewDecision)
admin.site.register(AuditEvent)
admin.site.register(UserMembership)


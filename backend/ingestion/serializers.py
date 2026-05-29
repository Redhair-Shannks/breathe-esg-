from rest_framework import serializers

from .models import (
    ActivityRecord,
    AuditEvent,
    EmissionEstimate,
    Facility,
    IngestionBatch,
    RawSourceRecord,
    ReferenceMapping,
    SourceSystem,
    Tenant,
    ValidationIssue,
)


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug"]


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ["id", "name", "code", "city", "country", "grid_region"]


class SourceSystemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceSystem
        fields = ["id", "kind", "name", "description", "is_active"]


class ReferenceMappingSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)

    class Meta:
        model = ReferenceMapping
        fields = [
            "id",
            "mapping_type",
            "source_value",
            "normalized_code",
            "display_name",
            "facility",
            "facility_name",
            "metadata",
        ]


class ValidationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationIssue
        fields = ["id", "severity", "code", "field", "message", "status", "created_at"]


class EmissionEstimateSerializer(serializers.ModelSerializer):
    factor_label = serializers.CharField(source="factor.label", read_only=True)
    factor_source = serializers.CharField(source="factor.source", read_only=True)

    class Meta:
        model = EmissionEstimate
        fields = ["co2e_kg", "calculation_note", "factor_label", "factor_source", "updated_at"]


class RawSourceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawSourceRecord
        fields = ["id", "row_number", "source_external_id", "row_hash", "payload", "received_at"]


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    activity_id = serializers.SerializerMethodField()
    activity_label = serializers.SerializerMethodField()
    activity_status = serializers.SerializerMethodField()
    source_kind = serializers.SerializerMethodField()
    batch_file = serializers.SerializerMethodField()
    row_number = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "event_type",
            "actor_name",
            "activity_id",
            "activity_label",
            "activity_status",
            "source_kind",
            "batch_file",
            "row_number",
            "before",
            "after",
            "note",
            "created_at",
        ]

    def get_actor_name(self, obj):
        return obj.actor.get_username() if obj.actor else "system"

    def get_activity_id(self, obj):
        return obj.activity_id

    def get_activity_label(self, obj):
        if not obj.activity:
            return "Batch event"
        return obj.activity.category or obj.activity.description or obj.activity.activity_kind

    def get_activity_status(self, obj):
        return obj.activity.review_status if obj.activity else ""

    def get_source_kind(self, obj):
        return obj.activity.source_system.kind if obj.activity else ""

    def get_batch_file(self, obj):
        if obj.batch:
            return obj.batch.file_name
        if obj.activity:
            return obj.activity.batch.file_name
        return ""

    def get_row_number(self, obj):
        if obj.activity and obj.activity.raw_record:
            return obj.activity.raw_record.row_number
        return None


class ActivityRecordSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source="facility.name", read_only=True)
    facility_code = serializers.CharField(source="facility.code", read_only=True)
    source_kind = serializers.CharField(source="source_system.kind", read_only=True)
    source_name = serializers.CharField(source="source_system.name", read_only=True)
    batch_file = serializers.CharField(source="batch.file_name", read_only=True)
    validation_issues = ValidationIssueSerializer(many=True, read_only=True)
    emission_estimate = EmissionEstimateSerializer(read_only=True)
    raw_record = RawSourceRecordSerializer(read_only=True)
    audit_events = AuditEventSerializer(many=True, read_only=True)

    class Meta:
        model = ActivityRecord
        fields = [
            "id",
            "external_id",
            "source_kind",
            "source_name",
            "batch_file",
            "activity_kind",
            "scope",
            "facility",
            "facility_name",
            "facility_code",
            "activity_date",
            "period_start",
            "period_end",
            "supplier",
            "category",
            "description",
            "original_quantity",
            "original_unit",
            "normalized_quantity",
            "normalized_unit",
            "amount",
            "currency",
            "origin",
            "destination",
            "review_status",
            "locked_at",
            "edited_from_raw",
            "metadata",
            "validation_issues",
            "emission_estimate",
            "raw_record",
            "audit_events",
        ]


class ActivityUpdateSerializer(serializers.ModelSerializer):
    note = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = ActivityRecord
        fields = [
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
            "note",
        ]


class IngestionBatchSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source_system.name", read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            "id",
            "source_kind",
            "source_name",
            "file_name",
            "parser_version",
            "status",
            "row_count",
            "imported_count",
            "failed_count",
            "warning_count",
            "started_at",
            "completed_at",
        ]


class UploadSerializer(serializers.Serializer):
    tenant = serializers.CharField(required=False, default="")
    source_kind = serializers.ChoiceField(choices=SourceSystem.Kind.choices)
    file = serializers.FileField()

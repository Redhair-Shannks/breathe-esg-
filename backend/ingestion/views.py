from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ActivityRecord, AuditEvent, Facility, IngestionBatch, ReferenceMapping, SourceSystem, Tenant, ValidationIssue
from .serializers import (
    ActivityRecordSerializer,
    ActivityUpdateSerializer,
    AuditEventSerializer,
    FacilitySerializer,
    IngestionBatchSerializer,
    ReferenceMappingSerializer,
    SourceSystemSerializer,
    TenantSerializer,
    UploadSerializer,
)
from .parsers import UploadFormatError
from .services import approve_activity, dashboard_summary, get_demo_user, get_tenant, process_upload, reject_activity, reopen_activity, update_activity


class TenantScopedMixin:
    def tenant(self):
        slug = self.request.query_params.get("tenant") or self.request.data.get("tenant")
        return get_tenant(slug)


class HealthAPIView(APIView):
    def get(self, request):
        return Response({"ok": True, "service": "breathe-esg-ingestion-prototype"})


class BootstrapAPIView(APIView):
    def get(self, request):
        tenant = get_tenant(request.query_params.get("tenant"))
        return Response(
            {
                "tenant": TenantSerializer(tenant).data,
                "tenants": TenantSerializer(Tenant.objects.all(), many=True).data,
                "facilities": FacilitySerializer(Facility.objects.filter(tenant=tenant), many=True).data,
                "source_systems": SourceSystemSerializer(SourceSystem.objects.filter(tenant=tenant), many=True).data,
                "summary": dashboard_summary(tenant),
            }
        )


class DashboardAPIView(APIView):
    def get(self, request):
        tenant = get_tenant(request.query_params.get("tenant"))
        recent_batches = IngestionBatch.objects.filter(tenant=tenant)[:8]
        top_issues = (
            ValidationIssue.objects.filter(tenant=tenant, status=ValidationIssue.Status.OPEN)
            .values("severity", "code")
            .annotate(rows=Count("id"))
            .order_by("severity", "-rows")[:10]
        )
        return Response(
            {
                "summary": dashboard_summary(tenant),
                "recent_batches": IngestionBatchSerializer(recent_batches, many=True).data,
                "top_issues": list(top_issues),
            }
        )


class TenantViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer


class FacilityViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = FacilitySerializer

    def get_queryset(self):
        return Facility.objects.filter(tenant=self.tenant())


class SourceSystemViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = SourceSystemSerializer

    def get_queryset(self):
        return SourceSystem.objects.filter(tenant=self.tenant())


class ReferenceMappingViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    serializer_class = ReferenceMappingSerializer

    def get_queryset(self):
        queryset = ReferenceMapping.objects.filter(tenant=self.tenant())
        mapping_type = self.request.query_params.get("mapping_type")
        if mapping_type:
            queryset = queryset.filter(mapping_type=mapping_type)
        return queryset

    def perform_create(self, serializer):
        serializer.save(tenant=self.tenant())


class IngestionBatchViewSet(TenantScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        return IngestionBatch.objects.filter(tenant=self.tenant()).select_related("source_system")

    def create(self, request, *args, **kwargs):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = get_tenant(serializer.validated_data.get("tenant") or request.query_params.get("tenant"))
        uploaded_file = serializer.validated_data["file"]
        try:
            batch = process_upload(
                tenant=tenant,
                source_kind=serializer.validated_data["source_kind"],
                uploaded_file=uploaded_file,
                file_name=uploaded_file.name,
                user=get_demo_user(request),
            )
        except UploadFormatError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ActivityRecordViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityRecordSerializer

    def get_queryset(self):
        queryset = (
            ActivityRecord.objects.filter(tenant=self.tenant())
            .select_related("facility", "batch", "source_system", "raw_record", "emission_estimate", "emission_estimate__factor")
            .prefetch_related("validation_issues", "audit_events")
        )
        source_kind = self.request.query_params.get("source_kind")
        review_status = self.request.query_params.get("review_status")
        severity = self.request.query_params.get("severity")
        search = self.request.query_params.get("q")
        if source_kind:
            queryset = queryset.filter(source_system__kind=source_kind)
        if review_status:
            queryset = queryset.filter(review_status=review_status)
        if severity:
            queryset = queryset.filter(validation_issues__severity=severity, validation_issues__status=ValidationIssue.Status.OPEN)
        if search:
            queryset = queryset.filter(description__icontains=search) | queryset.filter(category__icontains=search)
        return queryset.distinct()

    def partial_update(self, request, *args, **kwargs):
        activity = self.get_object()
        serializer = ActivityUpdateSerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data.pop("note", "")
        try:
            update_activity(activity, serializer.validated_data, user=get_demo_user(request), note=note)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(activity, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        activity = self.get_object()
        try:
            approve_activity(activity, user=get_demo_user(request), note=request.data.get("note", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(activity, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        activity = self.get_object()
        try:
            reject_activity(activity, user=get_demo_user(request), note=request.data.get("note", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(activity, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        activity = self.get_object()
        try:
            reopen_activity(activity, user=get_demo_user(request), note=request.data.get("note", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ActivityRecordSerializer(activity, context=self.get_serializer_context()).data)


class AuditEventViewSet(TenantScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        queryset = (
            AuditEvent.objects.filter(tenant=self.tenant())
            .select_related(
                "actor",
                "batch",
                "activity",
                "activity__batch",
                "activity__source_system",
                "activity__raw_record",
            )
            .order_by("-created_at", "-id")
        )
        activity_id = self.request.query_params.get("activity")
        event_type = self.request.query_params.get("event_type")
        if activity_id:
            queryset = queryset.filter(activity_id=activity_id)
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        return queryset

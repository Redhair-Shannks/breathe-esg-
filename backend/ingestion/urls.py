from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActivityRecordViewSet,
    AuditEventViewSet,
    BootstrapAPIView,
    DashboardAPIView,
    FacilityViewSet,
    HealthAPIView,
    IngestionBatchViewSet,
    ReferenceMappingViewSet,
    SourceSystemViewSet,
    TenantViewSet,
)


router = DefaultRouter()
router.register("tenants", TenantViewSet, basename="tenant")
router.register("facilities", FacilityViewSet, basename="facility")
router.register("source-systems", SourceSystemViewSet, basename="source-system")
router.register("mappings", ReferenceMappingViewSet, basename="mapping")
router.register("batches", IngestionBatchViewSet, basename="batch")
router.register("activities", ActivityRecordViewSet, basename="activity")
router.register("audit-events", AuditEventViewSet, basename="audit-event")

urlpatterns = [
    path("health/", HealthAPIView.as_view(), name="health"),
    path("bootstrap/", BootstrapAPIView.as_view(), name="bootstrap"),
    path("dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("", include(router.urls)),
]

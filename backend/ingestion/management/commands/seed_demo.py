from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ingestion.models import (
    ActivityRecord,
    AuditEvent,
    EmissionFactor,
    EmissionEstimate,
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
from ingestion.services import process_upload


class Command(BaseCommand):
    help = "Seed a realistic demo tenant, mappings, factors, and sample ingestion batches."

    def add_arguments(self, parser):
        parser.add_argument("--noinput", action="store_true", help="Run without prompts.")
        parser.add_argument("--reload", action="store_true", help="Clear existing demo data first.")

    def handle(self, *args, **options):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="analyst@demo.local", defaults={"email": "analyst@demo.local"})
        user.set_password("demo-password")
        user.is_staff = True
        user.is_superuser = True
        user.save()

        if options["reload"]:
            self._clear_demo_tenant()

        tenant, _ = Tenant.objects.get_or_create(slug="acme-manufacturing", defaults={"name": "ACME Manufacturing"})
        UserMembership.objects.get_or_create(user=user, tenant=tenant, defaults={"role": UserMembership.Role.ANALYST})

        denver, _ = Facility.objects.update_or_create(
            tenant=tenant,
            code="PL01",
            defaults={"name": "Denver Manufacturing Plant", "city": "Denver", "country": "US", "grid_region": "RFCE"},
        )
        berlin, _ = Facility.objects.update_or_create(
            tenant=tenant,
            code="DE10",
            defaults={"name": "Berlin Assembly Plant", "city": "Berlin", "country": "DE", "grid_region": "EU-DE"},
        )
        california, _ = Facility.objects.update_or_create(
            tenant=tenant,
            code="CA01",
            defaults={"name": "San Francisco Office", "city": "San Francisco", "country": "US", "grid_region": "CAMX"},
        )

        for kind, name, description in [
            (SourceSystem.Kind.SAP, "SAP S/4HANA export", "OData-like material document and purchase extract uploaded as CSV."),
            (SourceSystem.Kind.UTILITY, "Utility portal Green Button CSV", "Facilities team export with meter billing periods and kWh usage."),
            (SourceSystem.Kind.TRAVEL, "Concur approved expense export", "Approved travel expense export shaped after Concur financial documents."),
        ]:
            SourceSystem.objects.update_or_create(
                tenant=tenant,
                kind=kind,
                name=name,
                defaults={"description": description, "is_active": True},
            )

        self._mapping(tenant, ReferenceMapping.MappingType.PLANT_CODE, "PL01", "PL01", "Denver Manufacturing Plant", denver)
        self._mapping(tenant, ReferenceMapping.MappingType.PLANT_CODE, "DE10", "DE10", "Berlin Assembly Plant", berlin)
        self._mapping(tenant, ReferenceMapping.MappingType.PLANT_CODE, "CA01", "CA01", "San Francisco Office", california)
        self._mapping(tenant, ReferenceMapping.MappingType.METER_ID, "MTR-DEN-001", "PL01-ELEC", "Denver main electric meter", denver)
        self._mapping(tenant, ReferenceMapping.MappingType.METER_ID, "MTR-CA-201", "CA01-ELEC", "San Francisco office meter", california)

        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "100045",
            "DIESEL_BULK",
            "Diesel fuel",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FUEL, "scope": ActivityRecord.Scope.SCOPE_1, "canonical_unit": "L"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-DIESEL-01",
            "DIESEL_BULK",
            "Diesel fuel",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FUEL, "scope": ActivityRecord.Scope.SCOPE_1, "canonical_unit": "L"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "200011",
            "NATURAL_GAS",
            "Natural gas",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FUEL, "scope": ActivityRecord.Scope.SCOPE_1, "canonical_unit": "m3"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-NG-01",
            "NATURAL_GAS",
            "Natural gas",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FUEL, "scope": ActivityRecord.Scope.SCOPE_1, "canonical_unit": "m3"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-GAS-02",
            "NATURAL_GAS",
            "Compressed gas",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FUEL, "scope": ActivityRecord.Scope.SCOPE_1, "canonical_unit": "m3"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "300310",
            "STEEL_COIL",
            "Steel coil procurement",
            metadata={"activity_kind": ActivityRecord.ActivityKind.PROCUREMENT, "scope": ActivityRecord.Scope.SCOPE_3, "canonical_unit": "kg"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-STEEL-02",
            "STEEL_COIL",
            "Steel coil procurement",
            metadata={"activity_kind": ActivityRecord.ActivityKind.PROCUREMENT, "scope": ActivityRecord.Scope.SCOPE_3, "canonical_unit": "kg"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-SOLVENT-01",
            "CLEANING_SOLVENT",
            "Cleaning solvent procurement",
            metadata={"activity_kind": ActivityRecord.ActivityKind.PROCUREMENT, "scope": ActivityRecord.Scope.SCOPE_3, "canonical_unit": "L"},
        )
        self._mapping(
            tenant,
            ReferenceMapping.MappingType.MATERIAL_CODE,
            "MAT-LUBE-01",
            "LUBRICANT_OIL",
            "Lubricant oil procurement",
            metadata={"activity_kind": ActivityRecord.ActivityKind.PROCUREMENT, "scope": ActivityRecord.Scope.SCOPE_3, "canonical_unit": "L"},
        )

        for source, display, kind in [
            ("Airfare", "Commercial flight", ActivityRecord.ActivityKind.FLIGHT),
            ("Hotel", "Hotel stay", ActivityRecord.ActivityKind.HOTEL),
            ("Taxi/Rideshare", "Taxi or rideshare", ActivityRecord.ActivityKind.GROUND),
            ("Rail", "Passenger rail", ActivityRecord.ActivityKind.GROUND),
        ]:
            self._mapping(
                tenant,
                ReferenceMapping.MappingType.EXPENSE_TYPE,
                source,
                source.upper().replace("/", "_").replace(" ", "_"),
                display,
                metadata={"activity_kind": kind, "scope": ActivityRecord.Scope.SCOPE_3},
            )

        for code, city, lat, lon in [
            ("DEN", "Denver International", 39.8561, -104.6737),
            ("SFO", "San Francisco International", 37.6213, -122.3790),
            ("JFK", "New York JFK", 40.6413, -73.7781),
            ("LHR", "London Heathrow", 51.4700, -0.4543),
            ("BLR", "Bengaluru Kempegowda", 13.1986, 77.7066),
            ("FRA", "Frankfurt Airport", 50.0379, 8.5622),
        ]:
            self._mapping(
                tenant,
                ReferenceMapping.MappingType.AIRPORT_CODE,
                code,
                code,
                city,
                metadata={"lat": lat, "lon": lon},
            )

        self._factor(ActivityRecord.ActivityKind.FUEL, ActivityRecord.Scope.SCOPE_1, "Diesel fuel", "L", "2.68000000", "")
        self._factor(ActivityRecord.ActivityKind.FUEL, ActivityRecord.Scope.SCOPE_1, "Natural gas", "m3", "2.03000000", "")
        self._factor(ActivityRecord.ActivityKind.ELECTRICITY, ActivityRecord.Scope.SCOPE_2, "Purchased electricity RFCE", "kWh", "0.37000000", "RFCE")
        self._factor(ActivityRecord.ActivityKind.ELECTRICITY, ActivityRecord.Scope.SCOPE_2, "Purchased electricity CAMX", "kWh", "0.20000000", "CAMX")
        self._factor(ActivityRecord.ActivityKind.ELECTRICITY, ActivityRecord.Scope.SCOPE_2, "Purchased electricity fallback", "kWh", "0.39000000", "")
        self._factor(ActivityRecord.ActivityKind.FLIGHT, ActivityRecord.Scope.SCOPE_3, "Passenger flight distance", "km", "0.15600000", "")
        self._factor(ActivityRecord.ActivityKind.HOTEL, ActivityRecord.Scope.SCOPE_3, "Hotel night", "night", "17.00000000", "")
        self._factor(ActivityRecord.ActivityKind.GROUND, ActivityRecord.Scope.SCOPE_3, "Ground transport distance", "km", "0.19200000", "")
        self._factor(ActivityRecord.ActivityKind.PROCUREMENT, ActivityRecord.Scope.SCOPE_3, "Steel procurement", "kg", "1.90000000", "")

        if not tenant.batches.exists():
            sample_root = Path(__file__).resolve().parents[4] / "sample_data"
            for source_kind, file_name in [
                (SourceSystem.Kind.SAP, "sap_fuel_procurement.csv"),
                (SourceSystem.Kind.UTILITY, "utility_green_button_electricity.csv"),
                (SourceSystem.Kind.TRAVEL, "concur_travel_expenses.csv"),
            ]:
                with (sample_root / file_name).open("rb") as handle:
                    process_upload(
                        tenant=tenant,
                        source_kind=source_kind,
                        uploaded_file=handle,
                        file_name=file_name,
                        user=user,
                    )

        self.stdout.write(self.style.SUCCESS("Seeded demo tenant acme-manufacturing."))
        self.stdout.write("Login: analyst@demo.local / demo-password")

    def _mapping(self, tenant, mapping_type, source_value, normalized_code, display_name, facility=None, metadata=None):
        ReferenceMapping.objects.update_or_create(
            tenant=tenant,
            mapping_type=mapping_type,
            source_value=source_value,
            defaults={
                "normalized_code": normalized_code,
                "display_name": display_name,
                "facility": facility,
                "metadata": metadata or {},
            },
        )

    def _factor(self, activity_kind, scope, label, unit, value, geography):
        EmissionFactor.objects.update_or_create(
            activity_kind=activity_kind,
            scope=scope,
            label=label,
            geography=geography,
            defaults={
                "factor_unit": unit,
                "kg_co2e_per_unit": Decimal(value),
                "source": "Prototype factor library based on EPA/GHG Protocol reporting categories",
                "source_url": "https://www.epa.gov/climateleadership/ghg-emission-factors-hub",
                "effective_from": date(2025, 1, 1),
                "metadata": {"note": "Illustrative seed factor; production should load the exact published factor workbook version."},
            },
        )

    def _clear_demo_tenant(self):
        tenant = Tenant.objects.filter(slug="acme-manufacturing").first()
        if not tenant:
            return

        # Source systems are protected by ingested records, so clear lineage-bearing
        # demo rows first. This keeps --reload repeatable without weakening the model.
        AuditEvent.objects.filter(tenant=tenant).delete()
        ReviewDecision.objects.filter(tenant=tenant).delete()
        ValidationIssue.objects.filter(tenant=tenant).delete()
        EmissionEstimate.objects.filter(activity__tenant=tenant).delete()
        ActivityRecord.objects.filter(tenant=tenant).delete()
        RawSourceRecord.objects.filter(tenant=tenant).delete()
        IngestionBatch.objects.filter(tenant=tenant).delete()
        SourceSystem.objects.filter(tenant=tenant).delete()
        ReferenceMapping.objects.filter(tenant=tenant).delete()
        EmissionFactor.objects.filter(tenant=tenant).delete()
        Facility.objects.filter(tenant=tenant).delete()
        UserMembership.objects.filter(tenant=tenant).delete()
        tenant.delete()

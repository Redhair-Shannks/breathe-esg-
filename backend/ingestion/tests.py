from decimal import Decimal

from django.test import TestCase

from .models import ActivityRecord, Facility, ReferenceMapping, Tenant
from .parsers import infer_source_kind, normalize_quantity, parse_date, parse_sap_row, parse_travel_row, parse_utility_row


class ParserPrimitiveTests(TestCase):
    def test_parse_dates_from_enterprise_export_formats(self):
        self.assertEqual(parse_date("2026-01-18").isoformat(), "2026-01-18")
        self.assertEqual(parse_date("15.01.2026").isoformat(), "2026-01-15")
        self.assertEqual(parse_date("20260121").isoformat(), "2026-01-21")

    def test_normalize_common_units(self):
        gallons, unit, issue = normalize_quantity(Decimal("10"), "GAL")
        self.assertIsNone(issue)
        self.assertEqual(unit, "L")
        self.assertEqual(gallons.quantize(Decimal("0.0001")), Decimal("37.8541"))

        miles, unit, issue = normalize_quantity(Decimal("100"), "mi")
        self.assertIsNone(issue)
        self.assertEqual(unit, "km")
        self.assertEqual(miles.quantize(Decimal("0.0001")), Decimal("160.9340"))

    def test_infer_source_kind_from_travel_export_headers(self):
        source_kind = infer_source_kind(
            [
                {
                    "Expense Report ID": "TRV-9009",
                    "Employee ID": "EMP-134",
                    "Travel Type": "Hotel",
                    "Origin Airport": "LHR",
                    "Destination Airport": "LHR",
                }
            ]
        )
        self.assertEqual(source_kind, "TRAVEL")

    def test_infer_source_kind_from_utility_export_headers(self):
        source_kind = infer_source_kind(
            [
                {
                    "Bill ID": "UTL-7001",
                    "Facility Code": "PL01",
                    "Meter Name": "Utility Meter 1",
                    "Billing Start": "2026-03-01",
                    "Billing End": "2026-03-31",
                    "Usage Unit": "kWh",
                }
            ]
        )
        self.assertEqual(source_kind, "UTILITY")


class SourceParserTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="ACME", slug="acme")
        self.facility = Facility.objects.create(
            tenant=self.tenant,
            name="Denver Plant",
            code="PL01",
            grid_region="RFCE",
        )
        ReferenceMapping.objects.create(
            tenant=self.tenant,
            mapping_type=ReferenceMapping.MappingType.PLANT_CODE,
            source_value="PL01",
            normalized_code="PL01",
            display_name="Denver Plant",
            facility=self.facility,
        )
        ReferenceMapping.objects.create(
            tenant=self.tenant,
            mapping_type=ReferenceMapping.MappingType.MATERIAL_CODE,
            source_value="100045",
            normalized_code="DIESEL",
            display_name="Diesel",
            metadata={
                "activity_kind": ActivityRecord.ActivityKind.FUEL,
                "scope": ActivityRecord.Scope.SCOPE_1,
                "canonical_unit": "L",
            },
        )
        ReferenceMapping.objects.create(
            tenant=self.tenant,
            mapping_type=ReferenceMapping.MappingType.METER_ID,
            source_value="MTR-DEN-001",
            normalized_code="PL01-ELEC",
            display_name="Denver meter",
            facility=self.facility,
        )
        ReferenceMapping.objects.create(
            tenant=self.tenant,
            mapping_type=ReferenceMapping.MappingType.EXPENSE_TYPE,
            source_value="Airfare",
            normalized_code="AIRFARE",
            display_name="Flight",
            metadata={"activity_kind": ActivityRecord.ActivityKind.FLIGHT},
        )
        ReferenceMapping.objects.create(
            tenant=self.tenant,
            mapping_type=ReferenceMapping.MappingType.EXPENSE_TYPE,
            source_value="Hotel",
            normalized_code="HOTEL",
            display_name="Hotel stay",
            metadata={"activity_kind": ActivityRecord.ActivityKind.HOTEL},
        )
        for code, lat, lon in [("DEN", 39.8561, -104.6737), ("SFO", 37.6213, -122.3790)]:
            ReferenceMapping.objects.create(
                tenant=self.tenant,
                mapping_type=ReferenceMapping.MappingType.AIRPORT_CODE,
                source_value=code,
                normalized_code=code,
                display_name=code,
                metadata={"lat": lat, "lon": lon},
            )

    def test_sap_german_headers_become_scope_1_fuel(self):
        parsed = parse_sap_row(
            self.tenant,
            {
                "Werk": "PL01",
                "Buchungsdatum": "15.01.2026",
                "Material": "100045",
                "Materialkurztext": "Diesel refill",
                "Menge": "10",
                "ME": "GAL",
                "Belegnummer": "4900001",
            },
        )
        self.assertEqual(parsed.data["scope"], ActivityRecord.Scope.SCOPE_1)
        self.assertEqual(parsed.data["activity_kind"], ActivityRecord.ActivityKind.FUEL)
        self.assertEqual(parsed.data["normalized_unit"], "L")
        self.assertFalse([issue for issue in parsed.issues if issue.severity == "ERROR"])

    def test_sap_researched_procurement_fields_are_preserved(self):
        parsed = parse_sap_row(
            self.tenant,
            {
                "Plant": "PL01",
                "Posting Date": "2026-01-15",
                "Document Date": "2026-01-14",
                "Company Code": "1000",
                "Material Code": "100045",
                "Quantity": "25",
                "Base UoM": "L",
                "Storage Location": "SL01",
                "Batch": "B-44",
                "Purchase Order": "45000077",
                "Purchase Order Item": "10",
                "Purchasing Organization": "P100",
                "Purchasing Group": "A01",
                "G/L Account": "540000",
                "Profit Center": "PC-01",
            },
        )
        metadata = parsed.data["metadata"]
        self.assertEqual(metadata["company_code"], "1000")
        self.assertEqual(metadata["storage_location"], "SL01")
        self.assertEqual(metadata["purchase_order_item"], "10")
        self.assertEqual(metadata["gl_account"], "540000")

    def test_utility_unknown_meter_blocks_review(self):
        parsed = parse_utility_row(
            self.tenant,
            {
                "Meter ID": "MTR-UNKNOWN",
                "Start Date": "2026-01-01",
                "End Date": "2026-01-31",
                "Usage": "1000",
                "Unit": "kWh",
            },
        )
        self.assertTrue(any(issue.code == "UNKNOWN_METER" for issue in parsed.issues))

    def test_utility_ai_export_uses_facility_fallback(self):
        parsed = parse_utility_row(
            self.tenant,
            {
                "Bill ID": "UTL-7002",
                "Facility Code": "PL01",
                "Facility Name": "Pune Manufacturing Plant",
                "Meter Name": "Utility Meter 1",
                "Tariff": "Large General Service",
                "Billing Start": "2026-03-01",
                "Billing End": "2026-03-31",
                "Usage": "181000",
                "Usage Unit": "kWh",
                "Amount": "66970",
                "Currency": "INR",
            },
        )
        self.assertEqual(parsed.data["external_id"], "UTL-7002")
        self.assertEqual(parsed.data["facility"], self.facility)
        self.assertEqual(parsed.data["normalized_unit"], "kWh")
        self.assertTrue(any(issue.code == "METER_ID_MISSING" for issue in parsed.issues))
        self.assertFalse([issue for issue in parsed.issues if issue.severity == "ERROR"])

    def test_utility_ai_export_flags_zero_usage(self):
        parsed = parse_utility_row(
            self.tenant,
            {
                "Bill ID": "UTL-7006",
                "Facility Code": "PL01",
                "Meter Name": "Utility Meter 1",
                "Billing Start": "2026-04-01",
                "Billing End": "2026-04-30",
                "Usage": "0",
                "Usage Unit": "kWh",
                "Review Status": "Blocked",
            },
        )
        codes = {issue.code for issue in parsed.issues}
        self.assertIn("ZERO_USAGE", codes)
        self.assertIn("SOURCE_MARKED_BLOCKED", codes)

    def test_utility_researched_bill_fields_are_preserved(self):
        parsed = parse_utility_row(
            self.tenant,
            {
                "Bill ID": "UTL-8001",
                "Custom Meter ID": "MTR-DEN-001",
                "Premise ID": "PREM-9",
                "Rate Schedule": "Large General Service",
                "Service Class": "Industrial",
                "Bill Start Date": "2026-04-01",
                "Bill End Date": "2026-04-30",
                "Energy Consumption": "1000",
                "Consumption Unit": "kWh",
                "Electric Demand kW": "42",
                "Demand Cost": "105",
                "Energy Charge": "280",
                "Taxes": "19",
                "Read Type": "Estimated",
            },
        )
        metadata = parsed.data["metadata"]
        self.assertEqual(parsed.data["facility"], self.facility)
        self.assertEqual(metadata["premise_id"], "PREM-9")
        self.assertEqual(metadata["service_class"], "Industrial")
        self.assertEqual(metadata["demand_kw"], "42")
        self.assertTrue(any(issue.code == "ESTIMATED_READING" for issue in parsed.issues))

    def test_travel_flight_estimates_distance_from_airports(self):
        parsed = parse_travel_row(
            self.tenant,
            {
                "Expense Type": "Airfare",
                "Transaction Date": "2026-01-09",
                "Origin": "DEN",
                "Destination": "SFO",
            },
        )
        self.assertEqual(parsed.data["normalized_unit"], "km")
        self.assertGreater(parsed.data["normalized_quantity"], Decimal("1000"))

    def test_travel_ai_export_aliases_and_blocks_bad_hotel_nights(self):
        parsed = parse_travel_row(
            self.tenant,
            {
                "Expense Report ID": "TRV-9009",
                "Employee ID": "EMP-134",
                "Employee Name": "Kabir Jain",
                "Travel Type": "Hotel",
                "Origin Airport": "LHR",
                "Destination Airport": "LHR",
                "Vendor": "Ibis London",
                "Flight Number": "",
                "Trip Count": "0",
                "Distance": "0",
                "Distance Unit": "night",
                "Amount": "0",
                "Currency": "GBP",
                "Expense Category": "Hotel",
                "Start Date": "2026-03-21",
                "End Date": "2026-03-21",
                "Review Status": "Blocked",
            },
        )
        self.assertEqual(parsed.data["external_id"], "TRV-9009:Hotel:2026-03-21")
        self.assertEqual(parsed.data["activity_kind"], ActivityRecord.ActivityKind.HOTEL)
        self.assertEqual(parsed.data["scope"], ActivityRecord.Scope.SCOPE_3)
        self.assertTrue(any(issue.code == "BAD_NIGHTS" for issue in parsed.issues))

    def test_travel_researched_expense_and_itinerary_fields_are_preserved(self):
        parsed = parse_travel_row(
            self.tenant,
            {
                "Expense Report ID": "TRV-9010",
                "Expense Entry ID": "ENT-1",
                "Employee ID": "EMP-135",
                "Employee Name": "Asha Rao",
                "Department": "Sales",
                "Cost Center": "CC-SALES",
                "Project Code": "PRJ-7",
                "Expense Type ID": "AIRFR",
                "Expense Type": "Airfare",
                "Spend Category": "Travel",
                "Transaction Date": "2026-03-21",
                "Payment Type": "Company Card",
                "Merchant Category Code": "4511",
                "Origin IATA": "DEN",
                "Destination IATA": "SFO",
                "Flight Number": "UA123",
                "Airline": "United",
                "Ticket Number": "016000000001",
                "Booking ID": "BK-7",
                "Cabin Class": "Economy",
            },
        )
        metadata = parsed.data["metadata"]
        self.assertEqual(metadata["expense_type_id"], "AIRFR")
        self.assertEqual(metadata["payment_type"], "Company Card")
        self.assertEqual(metadata["ticket_number"], "016000000001")
        self.assertEqual(metadata["cabin_class"], "Economy")
        self.assertEqual(parsed.data["normalized_unit"], "km")

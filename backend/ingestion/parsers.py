import csv
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from .models import ActivityRecord, ReferenceMapping, ValidationIssue


class UploadFormatError(ValueError):
    pass


@dataclass
class ParserIssue:
    severity: str
    code: str
    message: str
    field: str = ""


@dataclass
class ParsedActivity:
    data: dict
    issues: list[ParserIssue] = field(default_factory=list)


def read_csv_rows(uploaded_file):
    raw = uploaded_file.read()
    if isinstance(raw, bytes) and raw.startswith(b"PK"):
        return read_xlsx_rows(raw)
    if isinstance(raw, str):
        text = raw
    else:
        text = decode_csv_bytes(raw)
    try:
        reader = csv.DictReader(io.StringIO(text))
        return clean_tabular_rows(reader)
    except csv.Error as exc:
        raise UploadFormatError(f"Could not parse upload as CSV: {exc}") from exc


def decode_csv_bytes(raw):
    if b"\x00" in raw[:4096]:
        for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise UploadFormatError("The uploaded file looks like binary data, not a CSV.")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UploadFormatError("Could not decode uploaded CSV.")


def clean_tabular_rows(rows):
    return [
        {str(key).strip(): value for key, value in row.items() if key is not None}
        for row in rows
        if any(str(value or "").strip() for key, value in row.items() if key is not None)
    ]


def read_xlsx_rows(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as workbook:
            worksheet_path = first_worksheet_path(workbook)
            shared_strings = load_shared_strings(workbook)
            date_style_ids = load_date_style_ids(workbook)
            rows = worksheet_rows(workbook, worksheet_path, shared_strings, date_style_ids)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise UploadFormatError("Could not parse upload as an .xlsx workbook.") from exc

    if not rows:
        return []
    headers = [str(value or "").strip() for value in rows[0]]
    if not any(headers):
        raise UploadFormatError("The first row of the workbook must contain column headers.")
    records = []
    for row in rows[1:]:
        record = {
            headers[index]: row[index] if index < len(row) else ""
            for index in range(len(headers))
            if headers[index]
        }
        if any(str(value or "").strip() for value in record.values()):
            records.append(record)
    return records


def first_worksheet_path(workbook):
    workbook_xml = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    rels_xml = ElementTree.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    first_sheet = workbook_xml.find("main:sheets/main:sheet", ns)
    if first_sheet is None:
        raise UploadFormatError("The workbook does not contain any sheets.")
    rel_id = first_sheet.attrib.get(f"{{{ns['rel']}}}id")
    for rel in rels_xml.findall("pkg:Relationship", ns):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    return "xl/worksheets/sheet1.xml"


def load_shared_strings(workbook):
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall("main:si", ns):
        parts = [node.text or "" for node in item.findall(".//main:t", ns)]
        strings.append("".join(parts))
    return strings


def load_date_style_ids(workbook):
    if "xl/styles.xml" not in workbook.namelist():
        return set()
    root = ElementTree.fromstring(workbook.read("xl/styles.xml"))
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    date_num_fmt_ids = {
        "14", "15", "16", "17", "22", "27", "30", "36", "45", "46", "47", "50", "57",
    }
    num_fmts = root.find("main:numFmts", ns)
    if num_fmts is not None:
        for fmt in num_fmts.findall("main:numFmt", ns):
            code = fmt.attrib.get("formatCode", "").lower()
            if any(token in code for token in ("yy", "mm", "dd", "date")):
                date_num_fmt_ids.add(fmt.attrib.get("numFmtId", ""))
    date_style_ids = set()
    cell_xfs = root.find("main:cellXfs", ns)
    if cell_xfs is not None:
        for index, xf in enumerate(cell_xfs.findall("main:xf", ns)):
            if xf.attrib.get("numFmtId") in date_num_fmt_ids:
                date_style_ids.add(str(index))
    return date_style_ids


def worksheet_rows(workbook, worksheet_path, shared_strings, date_style_ids):
    root = ElementTree.fromstring(workbook.read(worksheet_path))
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    output = []
    for row in root.findall(".//main:sheetData/main:row", ns):
        values = []
        for cell in row.findall("main:c", ns):
            column_index = column_number(cell.attrib.get("r", "")) - 1
            while len(values) < column_index:
                values.append("")
            values.append(cell_value(cell, shared_strings, date_style_ids, ns))
        output.append(values)
    return output


def column_number(cell_reference):
    letters = re.sub(r"[^A-Z]", "", cell_reference.upper())
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number or 1


def cell_value(cell, shared_strings, date_style_ids, ns):
    cell_type = cell.attrib.get("t")
    style_id = cell.attrib.get("s")
    value_node = cell.find("main:v", ns)
    raw_value = value_node.text if value_node is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError):
            return ""
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", ns))
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    if style_id in date_style_ids and raw_value:
        parsed_date = excel_serial_date(raw_value)
        if parsed_date:
            return parsed_date.isoformat()
    return raw_value


def excel_serial_date(raw_value):
    try:
        serial = float(raw_value)
    except ValueError:
        return None
    if serial <= 0:
        return None
    days = int(serial)
    if days >= 60:
        days -= 1
    return date(1899, 12, 31) + timedelta(days=days)


def stable_row_hash(row):
    canonical = json.dumps(row, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_headers(row, aliases):
    normalized = {}
    for header, value in row.items():
        canonical = aliases.get(_key(header), header)
        normalized[canonical] = value.strip() if isinstance(value, str) else value
    return normalized


def parse_decimal(value):
    if value is None or value == "":
        return None
    raw = str(value).strip().replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    if raw in {"", "-", "."}:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_date(value):
    if not value:
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%Y%m%d",
        "%d-%m-%Y",
        "%m-%d-%Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


UNIT_ALIASES = {
    "l": ("L", Decimal("1")),
    "ltr": ("L", Decimal("1")),
    "liter": ("L", Decimal("1")),
    "litre": ("L", Decimal("1")),
    "gal": ("L", Decimal("3.78541")),
    "gallon": ("L", Decimal("3.78541")),
    "gallons": ("L", Decimal("3.78541")),
    "kg": ("kg", Decimal("1")),
    "kilogram": ("kg", Decimal("1")),
    "kilograms": ("kg", Decimal("1")),
    "lb": ("kg", Decimal("0.453592")),
    "lbs": ("kg", Decimal("0.453592")),
    "ton": ("kg", Decimal("1000")),
    "tonne": ("kg", Decimal("1000")),
    "t": ("kg", Decimal("1000")),
    "m3": ("m3", Decimal("1")),
    "cbm": ("m3", Decimal("1")),
    "kwh": ("kWh", Decimal("1")),
    "mwh": ("kWh", Decimal("1000")),
    "kwhr": ("kWh", Decimal("1")),
    "km": ("km", Decimal("1")),
    "kilometer": ("km", Decimal("1")),
    "kilometre": ("km", Decimal("1")),
    "mi": ("km", Decimal("1.60934")),
    "mile": ("km", Decimal("1.60934")),
    "miles": ("km", Decimal("1.60934")),
    "night": ("night", Decimal("1")),
    "nights": ("night", Decimal("1")),
}


def normalize_quantity(quantity, unit):
    if quantity is None:
        return None, "", ParserIssue("ERROR", "MISSING_QUANTITY", "Quantity is missing.", "quantity")
    unit_key = _key(unit)
    if unit_key not in UNIT_ALIASES:
        return None, "", ParserIssue("ERROR", "UNSUPPORTED_UNIT", f"Unsupported unit '{unit}'.", "unit")
    canonical_unit, multiplier = UNIT_ALIASES[unit_key]
    return quantity * multiplier, canonical_unit, None


SAP_ALIASES = {
    "werk": "plant_code",
    "plant": "plant_code",
    "plantcode": "plant_code",
    "buchungsdatum": "posting_date",
    "postingdate": "posting_date",
    "documentdate": "document_date",
    "belegdatum": "document_date",
    "companycode": "company_code",
    "buchungskreis": "company_code",
    "material": "material_code",
    "materialcode": "material_code",
    "materialnumber": "material_code",
    "materialdocumentitem": "document_item",
    "item": "document_item",
    "materialkurztext": "material_description",
    "materialdescription": "material_description",
    "menge": "quantity",
    "quantity": "quantity",
    "me": "unit",
    "unit": "unit",
    "uom": "unit",
    "entryunit": "unit",
    "baseunitofmeasure": "unit",
    "baseuom": "unit",
    "bewegungsart": "movement_type",
    "movementtype": "movement_type",
    "belegnummer": "document_number",
    "documentnumber": "document_number",
    "materialdocument": "document_number",
    "materialdocumentyear": "document_year",
    "fiscalyear": "document_year",
    "storagelocation": "storage_location",
    "lagerort": "storage_location",
    "batch": "batch_number",
    "charge": "batch_number",
    "referencedocument": "reference_document",
    "referencedocumentitem": "reference_document_item",
    "kostenstelle": "cost_center",
    "costcenter": "cost_center",
    "glaccount": "gl_account",
    "g/laccount": "gl_account",
    "profitcenter": "profit_center",
    "wbselement": "wbs_element",
    "order": "internal_order",
    "internalorder": "internal_order",
    "fueltype": "fuel_type",
    "betrag": "amount",
    "amount": "amount",
    "netamount": "amount",
    "netpriceamount": "amount",
    "wahrung": "currency",
    "waehrung": "currency",
    "currency": "currency",
    "lieferant": "supplier",
    "vendor": "supplier",
    "supplier": "supplier",
    "suppliername": "supplier_name",
    "einkaufsbeleg": "purchase_order",
    "purchaseorder": "purchase_order",
    "purchaseorderitem": "purchase_order_item",
    "purchasingdocumentitem": "purchase_order_item",
    "purchasingorganization": "purchasing_organization",
    "purchasingorg": "purchasing_organization",
    "purchasinggroup": "purchasing_group",
}

UTILITY_ALIASES = {
    "billid": "bill_id",
    "accountnumber": "account_number",
    "account": "account_number",
    "utilityaccount": "account_number",
    "premiseid": "premise_id",
    "serviceagreement": "service_agreement",
    "facilitycode": "facility_code",
    "facilityname": "facility_name",
    "meterid": "meter_id",
    "meternumber": "meter_id",
    "custommeterid": "meter_id",
    "metername": "meter_name",
    "meterreadtype": "read_type",
    "readtype": "read_type",
    "estimated": "estimated",
    "estimate": "estimated",
    "serviceaddress": "service_address",
    "startdate": "period_start",
    "fromdate": "period_start",
    "billingstart": "period_start",
    "billstartdate": "period_start",
    "enddate": "period_end",
    "todate": "period_end",
    "billingend": "period_end",
    "billenddate": "period_end",
    "previousreaddate": "previous_read_date",
    "currentreaddate": "current_read_date",
    "previousreading": "previous_reading",
    "currentreading": "current_reading",
    "billperiodstart": "period_start",
    "billperiodend": "period_end",
    "usage": "quantity",
    "consumption": "quantity",
    "energyconsumption": "quantity",
    "unit": "unit",
    "usageunit": "unit",
    "consumptionunit": "unit",
    "uom": "unit",
    "demandkw": "demand_kw",
    "electricdemandkw": "demand_kw",
    "peakdemandkw": "demand_kw",
    "demand": "demand_kw",
    "demandcost": "demand_cost",
    "energycharge": "energy_charge",
    "taxes": "taxes",
    "tax": "taxes",
    "totalcharge": "amount",
    "totalcost": "amount",
    "amount": "amount",
    "currency": "currency",
    "tariff": "tariff",
    "rateschedule": "tariff",
    "serviceclass": "service_class",
    "touperiod": "tou_period",
    "timeofuseperiod": "tou_period",
    "reviewstatus": "source_review_status",
}

TRAVEL_ALIASES = {
    "reportid": "report_id",
    "expensereportid": "report_id",
    "entryid": "entry_id",
    "expenseentryid": "entry_id",
    "employeeid": "employee_id",
    "employee": "employee",
    "employeename": "employee",
    "department": "department",
    "costcenter": "cost_center",
    "projectcode": "project_code",
    "expensetype": "expense_type",
    "expensetypeid": "expense_type_id",
    "spendcategory": "spend_category",
    "spendcategorycode": "spend_category_code",
    "traveltype": "expense_type",
    "expensecategory": "expense_type",
    "transactiondate": "transaction_date",
    "posteddate": "posted_date",
    "paymentprocessingdate": "posted_date",
    "startdate": "start_date",
    "checkindate": "start_date",
    "pickup_date": "start_date",
    "enddate": "end_date",
    "checkoutdate": "end_date",
    "return_date": "end_date",
    "date": "transaction_date",
    "amount": "amount",
    "transactionamount": "amount",
    "approvedamount": "amount",
    "currency": "currency",
    "transactioncurrency": "currency",
    "paymenttype": "payment_type",
    "paymenttypename": "payment_type",
    "merchantcategorycode": "merchant_category_code",
    "origin": "origin",
    "originairport": "origin",
    "originiata": "origin",
    "from": "origin",
    "destination": "destination",
    "destinationairport": "destination",
    "destinationiata": "destination",
    "to": "destination",
    "distance": "distance",
    "distanceunit": "distance_unit",
    "nights": "nights",
    "nightcount": "nights",
    "tripcount": "trip_count",
    "vendor": "vendor",
    "merchant": "vendor",
    "flightnumber": "flight_number",
    "airline": "airline",
    "carrier": "airline",
    "ticketnumber": "ticket_number",
    "bookingid": "booking_id",
    "itineraryid": "itinerary_id",
    "cabinclass": "cabin_class",
    "bookingclass": "cabin_class",
    "fareclass": "fare_class",
    "hotelcity": "hotel_city",
    "hotelcountry": "hotel_country",
    "vehicleclass": "vehicle_class",
    "railoperator": "rail_operator",
    "reviewstatus": "source_review_status",
}


def find_mapping(tenant, mapping_type, source_value):
    if not source_value:
        return None
    return ReferenceMapping.objects.filter(
        tenant=tenant,
        mapping_type=mapping_type,
        source_value__iexact=str(source_value).strip(),
    ).first()


def parse_sap_row(tenant, row):
    row = normalize_headers(row, SAP_ALIASES)
    issues = []
    plant_code = row.get("plant_code", "")
    material_code = row.get("material_code", "")
    plant_mapping = find_mapping(tenant, ReferenceMapping.MappingType.PLANT_CODE, plant_code)
    material_mapping = find_mapping(tenant, ReferenceMapping.MappingType.MATERIAL_CODE, material_code)

    if not plant_mapping:
        issues.append(ParserIssue("ERROR", "UNKNOWN_PLANT", f"SAP plant '{plant_code}' is not mapped.", "plant_code"))
    if not material_mapping:
        issues.append(ParserIssue("ERROR", "UNKNOWN_MATERIAL", f"SAP material '{material_code}' is not mapped.", "material_code"))

    material_meta = material_mapping.metadata if material_mapping else {}
    activity_kind = material_meta.get("activity_kind", ActivityRecord.ActivityKind.PROCUREMENT)
    scope = material_meta.get("scope", ActivityRecord.Scope.SCOPE_3)
    quantity = parse_decimal(row.get("quantity"))
    normalized_quantity, normalized_unit, unit_issue = normalize_quantity(quantity, row.get("unit"))
    if unit_issue:
        issues.append(unit_issue)

    expected_unit = material_meta.get("canonical_unit")
    if expected_unit and normalized_unit and expected_unit != normalized_unit:
        issues.append(
            ParserIssue(
                "WARNING",
                "UNEXPECTED_UNIT",
                f"Expected {expected_unit} for material {material_code}, got {normalized_unit}.",
                "unit",
            )
        )

    activity_date = parse_date(row.get("posting_date"))
    if not activity_date:
        issues.append(ParserIssue("ERROR", "BAD_DATE", "Posting date could not be parsed.", "posting_date"))
    elif activity_date > date.today():
        issues.append(ParserIssue("WARNING", "FUTURE_DATE", "Posting date is in the future.", "posting_date"))

    if quantity is not None and quantity < 0:
        issues.append(ParserIssue("ERROR", "NEGATIVE_QUANTITY", "Quantity is negative.", "quantity"))
    elif quantity == 0:
        issues.append(ParserIssue("WARNING", "ZERO_QUANTITY", "Quantity is zero.", "quantity"))

    external_id = row.get("document_number") or row.get("purchase_order") or ""
    data = {
        "external_id": external_id,
        "activity_kind": activity_kind,
        "scope": scope,
        "facility": plant_mapping.facility if plant_mapping else None,
        "activity_date": activity_date,
        "period_start": activity_date,
        "period_end": activity_date,
        "supplier": row.get("supplier", ""),
        "category": material_mapping.display_name if material_mapping else row.get("material_description", ""),
        "description": row.get("material_description", "") or material_code,
        "original_quantity": quantity,
        "original_unit": row.get("unit", ""),
        "normalized_quantity": normalized_quantity,
        "normalized_unit": normalized_unit,
        "amount": parse_decimal(row.get("amount")),
        "currency": (row.get("currency") or "").upper()[:3],
        "metadata": {
            "plant_code": plant_code,
            "material_code": material_code,
            "company_code": row.get("company_code", ""),
            "document_date": row.get("document_date", ""),
            "document_year": row.get("document_year", ""),
            "document_item": row.get("document_item", ""),
            "movement_type": row.get("movement_type", ""),
            "storage_location": row.get("storage_location", ""),
            "batch_number": row.get("batch_number", ""),
            "reference_document": row.get("reference_document", ""),
            "reference_document_item": row.get("reference_document_item", ""),
            "cost_center": row.get("cost_center", ""),
            "gl_account": row.get("gl_account", ""),
            "profit_center": row.get("profit_center", ""),
            "wbs_element": row.get("wbs_element", ""),
            "internal_order": row.get("internal_order", ""),
            "fuel_type": row.get("fuel_type", ""),
            "supplier_name": row.get("supplier_name", ""),
            "purchase_order": row.get("purchase_order", ""),
            "purchase_order_item": row.get("purchase_order_item", ""),
            "purchasing_organization": row.get("purchasing_organization", ""),
            "purchasing_group": row.get("purchasing_group", ""),
            "source_shape": "SAP S/4HANA OData-like material document/purchase extract",
        },
    }
    return ParsedActivity(data=data, issues=issues)


def parse_utility_row(tenant, row):
    row = normalize_headers(row, UTILITY_ALIASES)
    issues = []
    meter_id = row.get("meter_id", "")
    meter_name = row.get("meter_name", "")
    facility_code = row.get("facility_code", "")
    meter_mapping = find_mapping(tenant, ReferenceMapping.MappingType.METER_ID, meter_id)
    facility_mapping = None
    if not meter_mapping and facility_code:
        facility_mapping = find_mapping(tenant, ReferenceMapping.MappingType.PLANT_CODE, facility_code)
    facility = (meter_mapping.facility if meter_mapping else None) or (facility_mapping.facility if facility_mapping else None)
    if not meter_mapping:
        if facility:
            issues.append(
                ParserIssue(
                    "INFO" if meter_name else "WARNING",
                    "METER_ID_MISSING",
                    "No mapped meter ID was provided; using facility code as the location fallback.",
                    "meter_id",
                )
            )
        elif facility_code:
            issues.append(ParserIssue("ERROR", "UNKNOWN_FACILITY", f"Facility code '{facility_code}' is not mapped.", "facility_code"))
        else:
            issues.append(ParserIssue("ERROR", "UNKNOWN_METER", "Utility row has no mapped meter ID or facility code.", "meter_id"))

    quantity = parse_decimal(row.get("quantity"))
    normalized_quantity, normalized_unit, unit_issue = normalize_quantity(quantity, row.get("unit"))
    if unit_issue:
        issues.append(unit_issue)
    if normalized_unit and normalized_unit != "kWh":
        issues.append(ParserIssue("ERROR", "UNSUPPORTED_ELECTRICITY_UNIT", "Electricity rows must normalize to kWh.", "unit"))

    period_start = parse_date(row.get("period_start"))
    period_end = parse_date(row.get("period_end"))
    if not period_start or not period_end:
        issues.append(ParserIssue("ERROR", "BAD_BILLING_PERIOD", "Billing start or end date could not be parsed.", "period"))
    elif period_end < period_start:
        issues.append(ParserIssue("ERROR", "BAD_BILLING_PERIOD", "Billing period ends before it starts.", "period"))
    elif (period_end - period_start).days > 65:
        issues.append(ParserIssue("WARNING", "LONG_BILLING_PERIOD", "Billing period is longer than 65 days.", "period"))

    if quantity is not None and quantity < 0:
        issues.append(ParserIssue("ERROR", "NEGATIVE_USAGE", "Electricity usage is negative.", "quantity"))
    elif quantity == 0:
        issues.append(ParserIssue("WARNING", "ZERO_USAGE", "Electricity usage is zero for the billing period.", "quantity"))
    if normalized_quantity is not None and normalized_quantity > Decimal("1000000"):
        issues.append(ParserIssue("WARNING", "HIGH_USAGE", "Electricity usage is unusually high for one billing period.", "quantity"))
    source_review_status = row.get("source_review_status", "")
    if "block" in source_review_status.lower() or "reject" in source_review_status.lower():
        issues.append(
            ParserIssue(
                "WARNING",
                "SOURCE_MARKED_BLOCKED",
                f"Source file review status is '{source_review_status}'.",
                "source_review_status",
            )
        )
    estimated_value = str(row.get("estimated", "") or row.get("read_type", "")).lower()
    if any(token in estimated_value for token in ("yes", "true", "estimated", "estimate", "est")):
        issues.append(
            ParserIssue(
                "WARNING",
                "ESTIMATED_READING",
                "Utility row appears to use an estimated meter reading.",
                "read_type",
            )
        )

    utility_meter_key = meter_id or f"{facility_code}:{meter_name}".strip(":") or row.get("account_number", "")

    data = {
        "external_id": row.get("bill_id") or f"{row.get('account_number', '')}:{utility_meter_key}:{period_start}:{period_end}",
        "activity_kind": ActivityRecord.ActivityKind.ELECTRICITY,
        "scope": ActivityRecord.Scope.SCOPE_2,
        "facility": facility,
        "activity_date": period_end,
        "period_start": period_start,
        "period_end": period_end,
        "supplier": row.get("utility", "") or "Utility portal export",
        "category": "Purchased electricity",
        "description": row.get("tariff", "") or row.get("service_address", "") or meter_name,
        "original_quantity": quantity,
        "original_unit": row.get("unit", ""),
        "normalized_quantity": normalized_quantity,
        "normalized_unit": normalized_unit,
        "amount": parse_decimal(row.get("amount")),
        "currency": (row.get("currency") or "USD").upper()[:3],
        "metadata": {
            "bill_id": row.get("bill_id", ""),
            "account_number": row.get("account_number", ""),
            "premise_id": row.get("premise_id", ""),
            "service_agreement": row.get("service_agreement", ""),
            "meter_id": meter_id,
            "meter_name": meter_name,
            "facility_code": facility_code,
            "facility_name": row.get("facility_name", ""),
            "utility_meter_key": utility_meter_key,
            "service_address": row.get("service_address", ""),
            "tariff": row.get("tariff", ""),
            "service_class": row.get("service_class", ""),
            "tou_period": row.get("tou_period", ""),
            "read_type": row.get("read_type", ""),
            "estimated": row.get("estimated", ""),
            "previous_read_date": row.get("previous_read_date", ""),
            "current_read_date": row.get("current_read_date", ""),
            "previous_reading": str(parse_decimal(row.get("previous_reading")) or ""),
            "current_reading": str(parse_decimal(row.get("current_reading")) or ""),
            "demand_kw": str(parse_decimal(row.get("demand_kw")) or ""),
            "demand_cost": str(parse_decimal(row.get("demand_cost")) or ""),
            "energy_charge": str(parse_decimal(row.get("energy_charge")) or ""),
            "taxes": str(parse_decimal(row.get("taxes")) or ""),
            "source_review_status": source_review_status,
            "source_shape": "Green Button / utility portal CSV billing-period export",
        },
    }
    return ParsedActivity(data=data, issues=issues)


def airport_distance_km(origin_mapping, destination_mapping):
    origin = origin_mapping.metadata
    destination = destination_mapping.metadata
    lat1 = float(origin["lat"])
    lon1 = float(origin["lon"])
    lat2 = float(destination["lat"])
    lon2 = float(destination["lon"])
    radius_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return Decimal(str(radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


def hotel_nights_from_row(row):
    explicit_nights = parse_decimal(row.get("nights"))
    if explicit_nights is not None:
        return explicit_nights
    trip_count = parse_decimal(row.get("trip_count"))
    if trip_count is not None:
        return trip_count
    start_date = parse_date(row.get("start_date") or row.get("transaction_date"))
    end_date = parse_date(row.get("end_date"))
    if start_date and end_date and end_date > start_date:
        return Decimal((end_date - start_date).days)
    return None


def parse_travel_row(tenant, row):
    row = normalize_headers(row, TRAVEL_ALIASES)
    issues = []
    expense_type = row.get("expense_type", "")
    expense_mapping = find_mapping(tenant, ReferenceMapping.MappingType.EXPENSE_TYPE, expense_type)
    if not expense_mapping:
        issues.append(ParserIssue("ERROR", "UNKNOWN_EXPENSE_TYPE", f"Travel expense type '{expense_type}' is not mapped.", "expense_type"))

    expense_meta = expense_mapping.metadata if expense_mapping else {}
    activity_kind = expense_meta.get("activity_kind", ActivityRecord.ActivityKind.GROUND)
    transaction_date = parse_date(row.get("transaction_date") or row.get("start_date"))
    if not transaction_date:
        issues.append(ParserIssue("ERROR", "BAD_DATE", "Transaction date could not be parsed.", "transaction_date"))
    if transaction_date and transaction_date > date.today():
        issues.append(ParserIssue("WARNING", "FUTURE_DATE", "Transaction date is in the future.", "transaction_date"))

    normalized_quantity = None
    normalized_unit = ""
    original_quantity = None
    original_unit = ""
    origin = (row.get("origin") or "").upper()
    destination = (row.get("destination") or "").upper()
    metadata = {
        "report_id": row.get("report_id", ""),
        "entry_id": row.get("entry_id", ""),
        "employee_id": row.get("employee_id", ""),
        "employee": row.get("employee", ""),
        "department": row.get("department", ""),
        "cost_center": row.get("cost_center", ""),
        "project_code": row.get("project_code", ""),
        "expense_type": expense_type,
        "expense_type_id": row.get("expense_type_id", ""),
        "spend_category": row.get("spend_category", ""),
        "spend_category_code": row.get("spend_category_code", ""),
        "posted_date": row.get("posted_date", ""),
        "payment_type": row.get("payment_type", ""),
        "merchant_category_code": row.get("merchant_category_code", ""),
        "flight_number": row.get("flight_number", ""),
        "airline": row.get("airline", ""),
        "ticket_number": row.get("ticket_number", ""),
        "booking_id": row.get("booking_id", ""),
        "itinerary_id": row.get("itinerary_id", ""),
        "cabin_class": row.get("cabin_class", ""),
        "fare_class": row.get("fare_class", ""),
        "hotel_city": row.get("hotel_city", ""),
        "hotel_country": row.get("hotel_country", ""),
        "vehicle_class": row.get("vehicle_class", ""),
        "rail_operator": row.get("rail_operator", ""),
        "source_review_status": row.get("source_review_status", ""),
        "start_date": row.get("start_date", ""),
        "end_date": row.get("end_date", ""),
        "source_shape": "SAP Concur-like approved expense report export",
    }

    if activity_kind == ActivityRecord.ActivityKind.HOTEL:
        original_quantity = hotel_nights_from_row(row)
        original_unit = "night"
        normalized_quantity, normalized_unit, unit_issue = normalize_quantity(original_quantity, "night")
        if unit_issue:
            issues.append(ParserIssue("ERROR", "MISSING_NIGHTS", "Hotel row has no usable night count.", "nights"))
        elif normalized_quantity <= 0:
            issues.append(ParserIssue("ERROR", "BAD_NIGHTS", "Hotel night count must be greater than zero.", "nights"))
    else:
        original_quantity = parse_decimal(row.get("distance"))
        original_unit = row.get("distance_unit") or "km"
        if original_quantity is not None:
            normalized_quantity, normalized_unit, unit_issue = normalize_quantity(original_quantity, original_unit)
            if unit_issue:
                issues.append(unit_issue)
        elif activity_kind == ActivityRecord.ActivityKind.FLIGHT and origin and destination:
            origin_mapping = find_mapping(tenant, ReferenceMapping.MappingType.AIRPORT_CODE, origin)
            destination_mapping = find_mapping(tenant, ReferenceMapping.MappingType.AIRPORT_CODE, destination)
            if origin_mapping and destination_mapping:
                normalized_quantity = airport_distance_km(origin_mapping, destination_mapping)
                normalized_unit = "km"
                original_unit = "airport_pair"
                metadata["distance_estimation"] = "great_circle_airport_distance"
            else:
                issues.append(ParserIssue("ERROR", "UNKNOWN_AIRPORT", "Airport code is not mapped.", "origin_destination"))
        else:
            issues.append(ParserIssue("WARNING", "MISSING_DISTANCE", "Distance is missing; emissions cannot be estimated.", "distance"))

    if activity_kind == ActivityRecord.ActivityKind.FLIGHT and origin and destination and origin == destination:
        issues.append(ParserIssue("WARNING", "SAME_AIRPORT", "Flight origin and destination are identical.", "origin_destination"))

    data = {
        "external_id": row.get("entry_id") or f"{row.get('report_id', '')}:{expense_type}:{transaction_date}",
        "activity_kind": activity_kind,
        "scope": ActivityRecord.Scope.SCOPE_3,
        "facility": None,
        "activity_date": transaction_date,
        "period_start": transaction_date,
        "period_end": transaction_date,
        "supplier": row.get("vendor", ""),
        "category": expense_mapping.display_name if expense_mapping else expense_type,
        "description": f"{expense_type} {origin}-{destination}".strip(),
        "original_quantity": original_quantity,
        "original_unit": original_unit,
        "normalized_quantity": normalized_quantity,
        "normalized_unit": normalized_unit,
        "amount": parse_decimal(row.get("amount")),
        "currency": (row.get("currency") or "USD").upper()[:3],
        "origin": origin,
        "destination": destination,
        "metadata": metadata,
    }
    return ParsedActivity(data=data, issues=issues)


PARSERS = {
    "SAP": parse_sap_row,
    "UTILITY": parse_utility_row,
    "TRAVEL": parse_travel_row,
}


SOURCE_HEADER_CUES = {
    "SAP": {
        "werk",
        "plant",
        "plantcode",
        "postingdate",
        "documentdate",
        "companycode",
        "buchungsdatum",
        "material",
        "materialcode",
        "materialnumber",
        "movementtype",
        "bewegungsart",
        "storagelocation",
        "purchaseorder",
        "purchasingorganization",
        "costcenter",
        "kostenstelle",
    },
    "UTILITY": {
        "billid",
        "accountnumber",
        "utilityaccount",
        "premiseid",
        "facilitycode",
        "facilityname",
        "meterid",
        "meternumber",
        "metername",
        "readtype",
        "estimated",
        "serviceaddress",
        "billingstart",
        "billingend",
        "billstartdate",
        "billenddate",
        "billperiodstart",
        "billperiodend",
        "usageunit",
        "consumptionunit",
        "demandkw",
        "electricdemandkw",
        "tariff",
        "rateschedule",
        "usage",
        "consumption",
    },
    "TRAVEL": {
        "reportid",
        "expensereportid",
        "entryid",
        "employeeid",
        "employeename",
        "expensetype",
        "expensetypeid",
        "spendcategory",
        "traveltype",
        "expensecategory",
        "originairport",
        "destinationairport",
        "originiata",
        "destinationiata",
        "tripcount",
        "flightnumber",
        "ticketnumber",
        "bookingid",
    },
}


def infer_source_kind(rows):
    if not rows:
        return ""
    header_keys = {_key(header) for header in rows[0].keys()}
    scores = {
        source_kind: len(header_keys.intersection(cues))
        for source_kind, cues in SOURCE_HEADER_CUES.items()
    }
    best_kind, best_score = max(scores.items(), key=lambda item: item[1])
    tied = [source_kind for source_kind, score in scores.items() if score == best_score]
    if best_score < 2 or len(tied) > 1:
        return ""
    return best_kind


def has_blocking_issue(issues):
    return any(issue.severity == ValidationIssue.Severity.ERROR for issue in issues)

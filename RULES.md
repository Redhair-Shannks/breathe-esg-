# RULES.md

## How The Rules Were Made

The validation rules are a mix of:

1. Rules directly backed by reporting standards or source-system documentation.
2. Conservative data-quality rules derived from realistic SAP, utility, and travel export shapes.
3. Prototype thresholds chosen for analyst triage, not final audit policy.

The key design choice is simple:

- `ERROR` means the row cannot be safely approved until fixed.
- `WARNING` means the row is parseable but suspicious.
- `INFO` means useful lineage context, not a review blocker.

## Status Assignment

During ingestion:

- Any row with at least one `ERROR` becomes `BLOCKED`.
- Rows with only `WARNING` or `INFO` issues become `NEEDS_REVIEW`.
- Rows with no issues also become `NEEDS_REVIEW`, because an analyst still needs to approve and lock them.
- Approval changes the row to `LOCKED`.
- Rejection changes the row to `REJECTED`.
- `LOCKED` and `REJECTED` cannot be edited, approved, or rejected again directly.
- Reopen is a separate action for correction workflows. It requires a note, returns the row to `NEEDS_REVIEW`, clears lock metadata, and records an `activity.reopened` audit event.

## Scope And Category Rules

| Rule | Status | Source basis |
| --- | --- | --- |
| Company fuel consumption maps to Scope 1 fuel | Mapping-driven | EPA says Scope 1 covers direct emissions from owned/controlled sources, including fuel combustion. |
| Purchased electricity maps to Scope 2 | Mapping-driven | EPA says Scope 2 covers purchased electricity, steam, heat, and cooling. |
| Procurement/material purchases map to Scope 3 Category 1 where mapped | Mapping-driven | GHG Protocol Scope 3 guidance identifies purchased goods and services as Category 1. |
| Flights, hotels, and ground transport map to Scope 3 Category 6 business travel | Mapping-driven | GHG Protocol Scope 3 guidance identifies business travel as Category 6. |
| Expense/material type must be mapped before confident classification | `ERROR` if unknown | Concur and SAP categories/materials are client-configurable, so local mapping is required. |

## SAP Rules

| Rule | Severity | Reason |
| --- | --- | --- |
| Unknown plant code | `ERROR` | Plant codes are meaningless without a tenant lookup table; facility/grid/location cannot be trusted. |
| Unknown material code | `ERROR` | Material code drives fuel/procurement category and expected unit. |
| Missing quantity | `ERROR` | No activity amount means no reliable emission estimate. |
| Unsupported unit | `ERROR` | Unit conversion must be deterministic. |
| Unparseable posting date | `ERROR` | Audit period and reporting year cannot be determined. |
| Negative quantity | `ERROR` | Could be a reversal/credit; prototype does not model adjustment documents yet. |
| Future posting date | `WARNING` | Possible forecast/test data or bad date entry. |
| Zero quantity | `WARNING` | Parseable but suspicious. |
| Unexpected but convertible unit | `WARNING` | Example: material expected liters but file supplies gallons; conversion works but analyst should review. |

Additional SAP fields are preserved as metadata, not used as approval blockers: company code, document date, material document item/year, storage location, batch, purchase order item, purchasing organization/group, G/L account, profit center, WBS element, and internal order.

## Utility Electricity Rules

| Rule | Severity | Reason |
| --- | --- | --- |
| Unknown meter and no facility fallback | `ERROR` | Row cannot be tied to a facility or grid region. |
| Unknown facility code | `ERROR` | Location cannot be trusted. |
| Missing quantity | `ERROR` | No kWh activity amount. |
| Unsupported unit | `ERROR` | Unit conversion must be deterministic. |
| Unit does not normalize to kWh | `ERROR` | This parser handles electricity consumption only. |
| Bad billing period dates | `ERROR` | Reporting period cannot be determined. |
| Billing end before start | `ERROR` | Invalid bill period. |
| Negative usage | `ERROR` | Could be net metering/credit/adjustment; prototype does not model these yet. |
| Billing period longer than 65 days | `WARNING` | ENERGY STAR Portfolio Manager flags energy meter entries over 65 days. |
| Overlapping billing periods | `WARNING` | ENERGY STAR flags overlaps; may double-count usage. |
| Usage more than 3x previous period | `WARNING` | Prototype triage threshold for spikes; should become configurable. |
| Zero usage | `WARNING` | Could be vacancy/shutoff, but needs review. |
| Very high usage over 1,000,000 kWh | `WARNING` | Prototype sanity check for unit mistakes, especially MWh/kWh confusion. |
| Estimated meter reading | `WARNING` | Estimated readings are valid evidence but lower confidence than actual readings. |
| Facility+meter name fallback instead of formal meter ID | `INFO` | Useful lineage, but not a blocker if facility is known. |

## Travel Rules

| Rule | Severity | Reason |
| --- | --- | --- |
| Unknown expense type | `ERROR` | Concur/Navan expense types are configurable; category and factor cannot be trusted. |
| Bad transaction/start date | `ERROR` | Reporting period cannot be determined. |
| Hotel nights missing | `ERROR` | Hotel emissions need nights, not only spend. |
| Hotel nights zero or negative | `ERROR` | Invalid hotel activity amount. |
| Flight distance missing but airport pair is known | No issue | Distance is estimated from airport coordinates. |
| Flight distance missing and airport code unknown | `ERROR` | Cannot estimate distance-based emissions. |
| Ground distance missing | `WARNING` | Row can be reviewed, but no distance-based estimate. |
| Future travel date | `WARNING` | Possible planned trip/test data. |
| Same flight origin and destination | `WARNING` | Possible data entry error. |

Additional travel fields are preserved as metadata: employee ID/name, department, cost center, project code, expense type ID, spend category, payment type, merchant category, booking ID, itinerary ID, ticket number, airline, flight number, cabin/fare class, hotel city/country, vehicle class, and rail operator.

## Emission Estimate Rules

| Rule | Severity | Reason |
| --- | --- | --- |
| No matching factor or no normalized quantity | `WARNING` | Analyst can still review source data, but estimate is incomplete. |
| Negative normalized quantity | `WARNING` via missing estimate plus source `ERROR` | Negative emissions are not produced because adjustment modeling is out of scope. |
| Electricity factor prefers facility grid region | Calculation rule | eGRID-style electricity accounting depends on geography. |
| Otherwise use fallback factor | Calculation rule | Prototype needs a demo estimate while preserving factor source. |

## Which Rules Are Research-Backed vs Derived

Research-backed:

- Scope 1/2/3 mappings.
- Scope 3 Category 1 and Category 6 choices.
- Electricity gaps/overlaps/long billing period concerns.
- Utility estimated-read handling.
- Need for source-specific mappings because SAP materials/plants and Concur expense types are configurable.
- Use of airport codes/distance for travel when distance is not provided.

Derived for prototype triage:

- Usage spike threshold of 3x previous period.
- Very high electricity threshold of 1,000,000 kWh.
- Zero usage as warning rather than blocker.
- Future date as warning rather than blocker.
- Same-airport flight as warning.
- Facility+meter-name fallback when formal meter ID is absent.

These derived rules are intentionally conservative and should be client-configurable in production.

## Sources Used

- EPA Scope 1 and Scope 2 Inventory Guidance: https://www.epa.gov/climateleadership/scope-1-and-scope-2-inventory-guidance
- EPA GHG Emission Factors Hub: https://www.epa.gov/climateleadership/ghg-emission-factors-hub
- EPA eGRID: https://www.epa.gov/egrid
- GHG Protocol Corporate Standard FAQ: https://ghgprotocol.org/corporate-standard-frequently-asked-questions
- GHG Protocol Scope 3 FAQ: https://ghgprotocol.org/scope-3-frequently-asked-questions-0
- GHG Protocol Scope 3 Category 1 guidance: https://ghgprotocol.org/sites/default/files/standards_supporting/Chapter1.pdf
- ENERGY STAR Portfolio Manager data collection worksheet: https://portfoliomanager.energystar.gov/pm/dataCollectionWorksheet
- ENERGY STAR Portfolio Manager web service release notes, meter alerts: https://portfoliomanager.energystar.gov/webservices/home/releaseNotes
- ENERGY STAR Data In guide: https://www.energystar.gov/sites/default/files/tools/EnergyStar_DataIn_508.pdf
- Green Button XML / ESPI structure: https://utilityapi.com/docs/greenbutton/xml
- Oracle Green Button Download My Data: https://docs.oracle.com/en/industries/utilities/digital-self-service/energy-management-overview/green-button-downloadmydata.html
- SAP IDoc architecture: https://help.sap.com/saphelp_gbt10/helpdata/en/4b/38625bad7f74fee10000000a421937/content.htm
- SAP Purchase Order OData V4 service: https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/91af7f8d3acd47da90d33aaacfcd0d59/c89eec80ec2043d980cb7b8c89e0a00a.html
- SAP Goods Movement document fields: https://api.sap.com/cdsviews/I_GOODSMOVEMENTDOCUMENTDEX/fields
- SAP Concur Financial Integration API: https://preview.developer.concur.com/api-reference/financial-integration/v4.financial-integration.html
- SAP Concur Expense Configuration API: https://preview.developer.concur.com/api-reference/expense/expense-config/v4.expense.config.html
- SAP Concur Report Entry Data: https://help.sap.com/docs/CONCUR_EXPENSE/bb83754b1c5541808d50c09901e11475/d4975d91f9e04d7c96defd095e441847.html
- SAP Concur Spend Categories: https://help.sap.com/docs/CONCUR_EXPENSE/1c6701a5b9ea4cc69eee62d00f2cf326/352423813ee84a3d912acb61edfb7114.html

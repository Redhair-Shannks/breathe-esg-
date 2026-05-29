# DECISIONS.md

## 1. SAP Ingestion

Decision: handle uploaded CSV/XLSX exports shaped after SAP S/4HANA OData/material document and purchase extracts.

Why: SAP IDocs are real, but they are segment-heavy and integration-specific. A four-day prototype claiming broad IDoc support would be dishonest. OData-style extracts and flat CSV/Excel exports are a realistic enterprise onboarding path because client teams often start by exporting material documents, purchase lines, plant codes, movement types, quantities, and units.

Handled:

- German and English column headers.
- plant code lookup.
- material code lookup.
- fuel rows as Scope 1.
- procurement rows as Scope 3.
- unit normalization for liters, gallons, kg, tonnes, and m3.
- optional SAP metadata: company code, document date, material document item/year, storage location, batch, reference document, purchase order item, purchasing organization/group, G/L account, profit center, WBS element, and internal order.
- bad dates, unknown plant, unknown material, negative quantity, unexpected units.

Ignored:

- full IDoc segment parsing.
- BAPI/RFC connectivity.
- SAP authorization and principal propagation.
- purchase order service pagination.
- multi-currency spend normalization.

PM question: Which SAP module/export does the client already have easiest access to: material documents, purchase order lines, goods movements, or IDocs from an integration team?

## 2. Utility Electricity Ingestion

Decision: handle Green Button / utility portal CSV/XLSX billing-period exports.

Why: Facilities teams commonly download usage/bill data from utility portals. PDF bills are common too, but OCR would dominate the prototype and distract from the core ingestion/review/audit model. Green Button-style exports are realistic because they include billing periods, meter IDs, usage units, and sometimes demand/cost fields.

Handled:

- meter ID to facility lookup.
- facility code plus meter name fallback when the export does not contain a true meter ID.
- billing start and end dates.
- kWh normalization.
- usage-unit aliases such as `Usage Unit`.
- tariff/rate schedule, service class, time-of-use period, demand kW, demand cost, energy charge, taxes, previous/current readings, and estimated-read metadata.
- overlapping billing periods.
- long billing periods.
- zero usage warnings.
- unusually high usage warnings.
- estimated meter-reading warnings.
- usage spikes versus previous period.
- unknown meters.

Ignored:

- PDF bill extraction.
- interval AMI data at 15-minute or hourly granularity.
- utility OAuth/API integrations.
- market-based Scope 2 instruments.
- demand-charge calculations.

PM question: Does the client need bill-level monthly reporting first, or interval-level energy analytics?

## 3. Corporate Travel Ingestion

Decision: handle Concur-like approved expense report exports, with an API-shaped source system but CSV/XLSX upload for the prototype.

Why: Concur exposes approved financial documents for ERP posting, and expense types are configurable. For emissions, the important normalization problem is mapping categories and deriving distance when platforms provide airport codes instead of miles. A CSV upload keeps the prototype deployable while preserving the same normalized flow that an API pull would use.

Handled:

- expense type mapping to flight, hotel, or ground transport.
- flights using airport-code distance when distance is missing.
- hotel nights.
- ground transport distance and miles-to-km conversion.
- optional expense and itinerary metadata: employee ID/name, department, cost center, project code, expense type ID, spend category, payment type, merchant category code, booking ID, itinerary ID, ticket number, airline, flight number, cabin/fare class, hotel city/country, vehicle class, and rail operator.
- unknown expense types.
- invalid hotel night counts.
- missing travel distance.

Ignored:

- live SAP Concur OAuth.
- itinerary/booking reconciliation.
- employee HR hierarchy.
- class-of-service radiative forcing factors.
- currency conversion.

PM question: Should travel emissions be based on booking itinerary, approved expense report, card transaction, or final reimbursed expense?

## 4. Analyst Review

Decision: build a single review queue across all sources.

Why: Analysts should not care whether the row came from SAP, a utility portal, or Concur when doing the core job: inspect what arrived, understand what failed, fix mappings, and approve rows.

Handled:

- source/status/severity filtering.
- row drawer with raw source payload.
- normalized field edits.
- validation issues.
- emission estimate and factor used.
- approve-and-lock.
- reject.
- reopen locked/rejected rows through a separate noted audit action.
- row-level audit timeline.
- tenant-wide audit trail modal with actor, source, row number, event type, note, and before/after payload.

Ignored:

- comments between analysts.
- task assignment.
- approval hierarchy.
- auditor-only portal.
- exporting the audit package as CSV/PDF.

PM question: Is one analyst approval enough, or do high-risk rows need two-person review?

## 4a. Unknown or Ambiguous File Shapes

Decision: do not attempt to magically parse every spreadsheet. The prototype supports declared source subsets plus common header aliases, then fails loudly when the selected source does not match the file.

Why: In real onboarding, unknown schemas require mapping work with the client. Silently guessing can create worse audit risk than rejecting the file. The system still preserves raw source rows for supported files, but if the analyst selects SAP and uploads a file whose headers clearly look like travel, the API returns a source-mismatch error.

Handled:

- common aliases such as `Travel Type`, `Expense Category`, `Origin Airport`, `Destination Airport`, `Trip Count`, `Start Date`, and `End Date`.
- source mismatch detection for SAP, utility, and travel header clues.
- row-level blocked issues when a recognized source has bad required data.

Ignored:

- arbitrary AI-generated columns with no source semantics.
- automatic source-type switching without analyst confirmation.
- LLM-based schema inference at upload time.

PM question: Should Breathe maintain a per-client mapping UI for new spreadsheet templates, or should new templates be configured by implementation engineers before ingestion?

## 4b. One File Per Source System, Multiple Categories Per File

Decision: each ingestion batch belongs to one source system: SAP, utility, or travel. Rows inside that batch may still map to different activity categories.

Why: The assignment describes three different upstream places where data lives: SAP, utility portals, and a corporate travel platform. Those systems have different schemas, dates, identifiers, and validation rules. Asking the analyst to choose the source system at upload time is realistic and reduces dangerous guessing. But row-level carbon categories should be mapping-driven, not manually chosen for every row.

Examples:

- One SAP upload can contain diesel fuel, natural gas, and steel procurement rows.
- One travel upload can contain flights, hotels, taxis, and rail rows.
- One utility upload should generally contain electricity meter/bill rows.

Ignored:

- one mega-workbook mixing SAP, travel, and utility tabs in a single upload.
- automatic splitting of mixed files by sheet.

PM question: Do enterprise clients usually provide separate exports by system, or do implementation teams receive combined onboarding workbooks that need sheet-level routing?

## 5. Emissions Calculation

Decision: include a small illustrative factor library and store the factor used for every estimate.

Why: The assignment is about ingestion and review, not building a complete carbon accounting engine. Still, analysts need enough calculation context to judge whether normalization worked.

Handled:

- kgCO2e estimates.
- factor unit matching.
- grid-region electricity factors.
- fallback factor when region is absent.

Ignored:

- CH4/N2O split gases.
- exact EPA workbook import.
- supplier-specific procurement factors.
- market-based electricity.
- uncertainty ranges.

PM question: Which factor hierarchy should win: client-supplied, supplier-specific, EPA/DEFRA, or spend-based fallback?

## 6. Authentication and Deployment

Decision: seed one demo analyst and keep API permissions simple.

Why: The data model supports membership and tenant scoping, but spending prototype time on production-grade auth would not improve the core evaluation areas as much as ingestion quality and auditability.

Handled:

- Django admin login.
- open prototype dashboard for reviewer convenience.
- seeded demo analyst used for upload/review audit events.
- tenant-scoped data model.
- demo tenant.
- deployable Render config.

Ignored:

- SSO.
- per-row authorization.
- organization invite flow.

PM question: For enterprise clients, should users authenticate through the client IdP, Breathe ESG's IdP, or both?

# MODEL.md

## Goal

The model is built around one core idea: source data and analyst-reviewed activity data are different things.

Enterprise ESG ingestion must preserve the original row exactly as received, then create a normalized activity row that analysts can review, edit, approve, and lock. Auditors care about both: what arrived from the source system and what the company ultimately reported.

## Tenancy

`Tenant` represents a client company. Every operational table has a `tenant_id`, including raw rows, normalized activities, mappings, factors, validation issues, batches, and audit events.

`UserMembership` links users to tenants with a role: admin, analyst, or auditor. The prototype keeps API permissions permissive for demo speed, but the data model is ready for tenant-scoped authorization.

Why: Breathe ESG serves multiple clients. Tenant separation has to be a first-class modeling concern, not a dashboard filter added later.

## Source Systems and Batches

`SourceSystem` stores the system that produced data:

- SAP fuel/procurement export
- Utility portal / Green Button electricity export
- Corporate travel / Concur-like expense export

`IngestionBatch` represents one upload or pull. It stores source kind, parser version, file name, status, row counts, warning counts, failed counts, creator, start time, and completion time.

Why: Analysts need to answer "what came in from where, when, and under which parser version?" Parser version matters because ingestion rules change.

## Raw Source of Truth

`RawSourceRecord` stores the exact row payload as JSON, row number, source external ID, and a SHA-256 row hash.

Raw records are immutable in normal use. Analysts do not edit them. They edit the normalized `ActivityRecord`.

Why: If an auditor asks why a value changed, we can show the original SAP/utility/travel row and every later analyst change.

## Normalized Activity

`ActivityRecord` is the common reviewable row. It stores:

- `activity_kind`: fuel, procurement, electricity, flight, hotel, ground transport
- `scope`: Scope 1, Scope 2, or Scope 3
- `facility`
- source date or billing period
- supplier/category/description
- original quantity and unit
- normalized quantity and unit
- amount and currency
- travel origin/destination
- review status
- lock timestamp
- raw source hash
- flexible metadata for source-specific details

I chose one normalized activity table instead of separate top-level tables for SAP, utilities, and travel because the analyst workflow is shared: validate, inspect raw row, edit normalized fields, estimate emissions, approve, lock. Source-specific details still exist in metadata and mappings.

## Scope Categorization

The prototype maps scopes as follows:

- SAP diesel/natural gas consumption by company-operated facilities: Scope 1.
- Purchased electricity from utility bills: Scope 2.
- Procurement materials: Scope 3 Category 1.
- Business travel flights/hotels/ground transport: Scope 3 Category 6.

Scope is stored on `ActivityRecord` so reporting queries do not need to infer scope repeatedly from source metadata.

## Facility and Reference Mappings

`Facility` stores plant/site/building identity, including plant code and grid region.

`ReferenceMapping` handles source values that are meaningless without client context:

- SAP plant code to facility
- SAP material code to activity kind, scope, and expected unit
- Utility meter ID to facility
- Travel expense type to activity kind
- Airport code to coordinates

Why: Real client data contains local codes. The ingestion system should not hard-code that PL01 means Denver or that material 100045 means diesel.

## Unit Normalization

The parser stores both:

- original quantity/unit from the source row
- normalized quantity/unit for factor matching

Examples:

- gallons to liters
- MWh to kWh
- pounds/tonnes to kg
- miles to km
- hotel nights to night

Unsupported units create blocking validation issues. Unexpected but convertible units create warnings when they disagree with a mapping's expected canonical unit.

## Emission Factors

`EmissionFactor` stores the activity kind, scope, factor unit, geography, effective dates, source, and factor value.

`EmissionEstimate` stores the factor used and the calculated kgCO2e for the activity.

Why: Estimates must be reproducible. If a factor changes next year, old rows still need to show which factor was used at approval time.

The demo seed factors are illustrative. A production deployment should import exact versioned factor tables from EPA/eGRID/DEFRA or client-approved factor sources.

## Validation and Suspicion Checks

`ValidationIssue` stores row-level errors and warnings.

Blocking examples:

- unknown SAP plant
- unknown SAP material
- unknown utility meter
- unsupported unit
- unparseable date
- negative quantity
- unknown travel expense type
- hotel row with zero nights

Warning examples:

- long utility billing period
- overlapping utility billing period
- electricity usage spike over 3x prior period
- missing travel distance when no airport fallback exists
- no emission estimate

Why: The analyst should not hunt through raw files to understand what went wrong. The system should produce a review queue.

## Review and Audit Trail

Review lifecycle:

1. Row is ingested as `NEEDS_REVIEW` or `BLOCKED`.
2. Analyst reviews raw row, normalized row, issues, and estimate.
3. Analyst can edit normalized fields before approval.
4. Every edit creates an `AuditEvent`.
5. Analyst approves the row.
6. Approval creates a `ReviewDecision` and locks the row by setting `review_status=LOCKED` and `locked_at`.

Locked rows cannot be edited or rejected through the API.

The UI exposes auditability in two places:

- the row drawer, showing lineage, raw source row, row hash, and row-level audit events.
- the tenant audit trail, showing recent ingest/edit/approve/reject events across batches and activities.

Why: Auditability is not only "we saved timestamps." It means approved evidence should be stable, and any change should be visible as a new event or adjustment.

## What This Model Is Ready For

- Replacing CSV uploads with API pulls while keeping the same batch/raw/activity flow.
- Adding market-based Scope 2 factors alongside location-based estimates.
- Adding supplier-specific Scope 3 factors.
- Adding review assignment and multi-analyst approval.
- Adding immutable adjustment rows for post-lock corrections.

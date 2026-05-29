# TRADEOFFS.md

## 1. I did not build live SAP, utility, or Concur integrations

Why: Real enterprise integrations need credentials, sandbox tenants, network allowlists, OAuth/client certificates, SAP module choices, and client-specific field mapping. In four days, a live integration would likely be shallow and brittle.

What I built instead: a batch/raw/normalized model where the transport layer is replaceable. CSV/XLSX upload is the prototype transport; later an SAP OData pull, Green Button Connect pull, or Concur API job can create the same `IngestionBatch` and `RawSourceRecord` rows.

## 2. I did not build PDF bill OCR

Why: Utility PDFs are realistic, but OCR/table extraction would consume too much time and create noisy edge cases unrelated to the central product question: can analysts trust, review, and approve normalized activity rows?

What I built instead: utility portal CSV/XLSX ingestion with billing periods, meter/facility fallback, tariffs, demand, kWh, estimated-read warnings, overlapping-period checks, long-period warnings, high-usage warnings, and usage-spike checks.

## 3. I did not build a full emissions-factor engine

Why: A complete factor engine needs versioned EPA/eGRID/DEFRA imports, market-based electricity, supplier-specific procurement factors, spend-based fallbacks, uncertainty, and factor governance. That is too large for this prototype.

What I built instead: a small versioned factor table that records the factor used on each estimate. The design supports replacing seed factors with exact published factor datasets later.

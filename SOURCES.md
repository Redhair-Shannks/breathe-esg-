# SOURCES.md

## SAP Fuel and Procurement

Researched formats:

- SAP S/4HANA OData services and Material Document API references.
- SAP IDoc structure and exchange concepts.

Sources:

- SAP Help Portal, OData services for SAP S/4HANA Cloud: https://help.sap.com/docs/SAP_S4HANA_CLOUD/3f57e7df4a114edabffe8b2d581a59ed/013f0f9ef9dc48daa3c4709ab8860333.html
- SAP Help Portal, IDoc architecture and concepts: https://help.sap.com/saphelp_gbt10/helpdata/en/4b/38625bad7f74fee10000000a421937/content.htm
- SAP Help Portal, Product master APIs and units of measure context: https://help.sap.com/docs/SAP_S4HANA_CLOUD/f86dc2eb1f8b48c880a7607213104b27/ccf66cce781c4a9a988d2553da64ffa5.html
- SAP Help Portal, Purchase Order OData V4 service: https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/91af7f8d3acd47da90d33aaacfcd0d59/c89eec80ec2043d980cb7b8c89e0a00a.html
- SAP Business Accelerator Hub, Goods Movement Document extraction fields: https://api.sap.com/cdsviews/I_GOODSMOVEMENTDOCUMENTDEX/fields

What I learned:

- SAP data is often not friendly for analytics in its native form.
- IDocs are realistic but segment-heavy and integration-specific.
- OData/API or flat exports are a more honest prototype target.
- Material and plant codes need lookup tables.
- Units of measure are explicit and cannot be assumed.
- Localized headers can appear depending on configuration and export language.
- Purchase order extracts commonly include company code, supplier, purchasing organization, purchasing group, document currency, and item-level purchasing fields.
- Goods movement/material document extracts commonly include movement type, plant, storage location, batch, posting/document dates, material document number/year/item, quantity, and base unit.
- Accounting allocation fields such as cost center, G/L account, profit center, WBS element, and internal order are useful for analyst review but are not enough on their own to classify carbon category.

Sample data:

`sample_data/sap_fuel_procurement.csv` contains:

- German headers like `Werk`, `Buchungsdatum`, `Menge`, `ME`, `Bewegungsart`.
- plant codes `PL01`, `DE10`, and an unmapped `PL99`.
- diesel, natural gas, steel procurement, and an unmapped material.
- dates in `15.01.2026`, `2026-01-18`, `01/20/2026`, and `20260121` formats.
- liters, gallons, kg, and m3.
- optional metadata fields such as company code, storage location, batch, purchase order item, purchasing organization/group, G/L account, profit center, WBS element, and internal order.

The importer also accepts `.xlsx` files when the first sheet is a simple header row plus data rows.

What would break in a real deployment:

- Client-specific SAP custom fields.
- IDoc segments not represented in a flat extract.
- multi-line purchase orders with tax/freight allocations.
- movement types that do not imply consumption.
- material codes whose emissions category depends on plant or vendor.

## Utility Electricity

Researched formats:

- Green Button Download My Data.
- Utility portal CSV/XML export behavior.
- electricity billing periods, meter IDs, usage units, and demand/cost fields.

Sources:

- Oracle Utilities Digital Self Service, Green Button Download My Data behavior: https://docs.oracle.com/en/industries/utilities/digital-self-service/energy-management-overview/green-button-downloadmydata.html
- Green Button XML format / ESPI structure: https://utilityapi.com/docs/greenbutton/xml
- ENERGY STAR Portfolio Manager data collection worksheet and meter-entry guidance: https://portfoliomanager.energystar.gov/pm/dataCollectionWorksheet
- US EPA eGRID: https://www.epa.gov/egrid
- US EPA GHG Emission Factors Hub: https://www.epa.gov/climateleadership/ghg-emission-factors-hub

What I learned:

- Facilities teams often start with utility portal downloads rather than APIs.
- Green Button-style exports can include CSV or XML.
- Downloads can be bill-period scoped.
- AMI customers can have interval exports, while non-AMI customers may only have billing data.
- Billing periods do not necessarily align with calendar months.
- Electricity factors depend on geography/grid region.
- Green Button-style data models include usage points/meters, tariff profile, interval blocks, interval readings, reading quality, time-of-use buckets, and interval cost.
- Portfolio Manager-style bill entry expects meter identity, start/end bill dates, usage, cost, demand kW, estimated-read flags, and alerts for gaps, overlaps, and entries longer than 65 days.

Sample data:

`sample_data/utility_green_button_electricity.csv` contains:

- account number.
- meter ID.
- facility and meter identifiers.
- service address.
- billing start/end dates.
- kWh usage.
- demand kW.
- total charge.
- tariff.
- demand kW, demand cost, energy charge, taxes, service class, rate schedule, read type, estimated-read flags, and previous/current readings when available.
- one overlapping billing period.
- one unusually long billing period.
- one unknown meter.

The same parser accepts `.xlsx` workbooks exported from a portal or edited by a facilities team.

For workbook variants that contain `Facility Code` and `Meter Name` but no formal meter ID, the prototype uses facility plus meter name as a fallback meter key and records that as an info issue. In production, the client should map those meter names to stable utility meter IDs.

What would break in a real deployment:

- zipped Green Button XML with nested interval readings.
- estimated reads versus actual reads.
- net metering or exported solar energy.
- multiple utility accounts per facility.
- meter changes mid-period.
- market-based Scope 2 certificates and supplier-specific factors.

## Corporate Travel

Researched formats:

- SAP Concur Financial Integration API.
- SAP Concur expense configuration APIs.
- approved expense reports and configurable expense types.

Sources:

- SAP Concur Developer Center, Financial Integration Service v4: https://preview.developer.concur.com/api-reference/financial-integration/v4.financial-integration.html
- SAP Concur Developer Center, Expense Configuration v4: https://preview.developer.concur.com/api-reference/expense/expense-config/v4.expense.config.html
- SAP Help Portal, Concur report entry data extract fields: https://help.sap.com/docs/CONCUR_EXPENSE/bb83754b1c5541808d50c09901e11475/c89376c016964053927f3f5474311d12.html
- Navan product pages reviewed for travel/expense domain shape: https://navan.com/product/expense-management
- GHG Protocol Scope 3 Standard: https://ghgprotocol.org/standards/scope-3-standard

What I learned:

- Concur financial integration is focused on approved financial documents for posting.
- Expense types are configurable, so the ingestion layer needs a mapping table.
- Travel rows may have spend, merchant, employee/report IDs, and category, but not always clean distance.
- Flight emissions often need airport-code distance fallback.
- Hotels need nights, not only amount.
- Concur configuration APIs expose expense type IDs/names, spend category codes/names, parent expense categories, payment types, policies, and group configuration.
- Concur financial integration is centered on approved financial documents, acknowledgements, posting confirmations, payment status, clearing amount, clearing currency, company code, and fiscal year.
- Travel management data may carry booking or itinerary context such as booking ID, itinerary ID, flight number, airline, ticket number, origin/destination IATA codes, cabin/fare class, hotel city/country, and vehicle/rail attributes.

Sample data:

`sample_data/concur_travel_expenses.csv` contains:

- report IDs and entry IDs.
- Airfare, Hotel, Taxi/Rideshare, and one unmapped Meal row.
- flights with airport codes but no distance.
- hotel stays with nights.
- ground transport with miles.
- one hotel row with zero nights.
- optional fields such as expense type ID, spend category, payment type, merchant category, department, cost center, project code, booking ID, ticket number, cabin class, airline, hotel city/country, and vehicle class.

The same parser accepts `.xlsx` workbooks for analyst-created or finance-exported travel files.

What would break in a real deployment:

- different expense type names per client.
- booked itinerary differing from reimbursed expense.
- airport codes missing or stored in free text.
- multi-leg flights.
- flight class and cabin factors.
- cancellations, refunds, and negative adjustments.

## Carbon Accounting References

Sources:

- GHG Protocol Corporate Standard: https://ghgprotocol.org/corporate-standard
- GHG Protocol Scope 3 Standard: https://ghgprotocol.org/standards/scope-3-standard
- US EPA GHG Emission Factors Hub: https://www.epa.gov/climateleadership/ghg-emission-factors-hub
- US EPA eGRID: https://www.epa.gov/egrid

How they influenced the prototype:

- Scope 1 fuel, Scope 2 purchased electricity, and Scope 3 business travel/procurement are explicit fields on the normalized activity.
- Emission factors are source/version-oriented rows, not constants hidden in code.
- Electricity factor lookup uses grid region when available.
- The demo factor values are illustrative seeds, not a substitute for importing exact published factor tables.

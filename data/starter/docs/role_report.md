# Role-based decision & exception report

Generated from the exported tables only. Each section is what that actor needs to act.

## Planner - top 15 shortages with the recommended mitigation

|   priority_rank | shortage_id       | sku_id     | location_id   | first_short_week   |   shortage_qty | primary_cause_code     | option_type       | supplier_id   |   fill_rate_pct |   total_cost |   cost_delta_vs_baseline | status   |
|----------------:|:------------------|:-----------|:--------------|:-------------------|---------------:|:-----------------------|:------------------|:--------------|----------------:|-------------:|-------------------------:|:---------|
|               1 | SHORT-2026-000012 | SKU-000045 | LOC-003       | 2026W01            |             42 | INBOUND_LATE_SUPPLIER  | EXPEDITE_PO       | SUP-0007      |          100    |       246.43 |                   -13.13 | PROPOSED |
|               2 | SHORT-2026-000024 | SKU-000082 | LOC-006       | 2026W02            |             16 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |          100    |        27    |                  -117.03 | PROPOSED |
|               3 | SHORT-2026-000029 | SKU-000099 | LOC-006       | 2026W09            |           1919 | INBOUND_CANCELLED      | NEW_PO            | SUP-0036      |          100    |      1207.91 |               -100656    | PROPOSED |
|               4 | SHORT-2026-000071 | SKU-000244 | LOC-009       | 2026W04            |             17 | INBOUND_QTY_SHORTFALL  | LOCATION_TRANSFER |               |          100    |        10.42 |                   -45.15 | PROPOSED |
|               5 | SHORT-2026-000048 | SKU-000150 | LOC-009       | 2026W03            |             53 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0034      |           66.67 |       171.7  |                  -290.93 | PROPOSED |
|               6 | SHORT-2026-000013 | SKU-000045 | LOC-010       | 2026W22            |           2054 | INBOUND_CANCELLED      | NEW_PO            | SUP-0007      |          100    |      1766.93 |               -391738    | PROPOSED |
|               7 | SHORT-2026-000016 | SKU-000061 | LOC-004       | 2026W02            |             27 | DEMAND_SPIKE           | LOCATION_TRANSFER |               |          100    |        54.83 |                  -237.59 | PROPOSED |
|               8 | SHORT-2026-000010 | SKU-000036 | LOC-008       | 2026W04            |             17 | INBOUND_LATE_SUPPLIER  | NEW_PO            | SUP-0012      |          100    |         5.17 |                   -23.5  | PROPOSED |
|               9 | SHORT-2026-000059 | SKU-000175 | LOC-002       | 2026W06            |            164 | INBOUND_LATE_TRANSPORT | NEW_PO            | SUP-0038      |          100    |        58.91 |                 -1398.98 | PROPOSED |
|              10 | SHORT-2026-000005 | SKU-000010 | LOC-002       | 2026W03            |              5 | INBOUND_QTY_SHORTFALL  | LOCATION_TRANSFER |               |          100    |         5.09 |                    -8.48 | PROPOSED |
|              11 | SHORT-2026-000075 | SKU-000258 | LOC-010       | 2026W02            |             21 | PRODUCTION_CAPACITY    | LOCATION_TRANSFER |               |           66.67 |         4.16 |                   -29.14 | PROPOSED |
|              12 | SHORT-2026-000080 | SKU-000261 | LOC-008       | 2026W01            |            279 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0002      |          100    |       631.6  |                  -190.89 | PROPOSED |
|              13 | SHORT-2026-000032 | SKU-000104 | LOC-002       | 2026W05            |            429 | INBOUND_CANCELLED      | NEW_PO            | SUP-0017      |          100    |       141.88 |                -32129.9  | PROPOSED |
|              14 | SHORT-2026-000011 | SKU-000041 | LOC-008       | 2026W04            |             93 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0025      |          100    |       138.93 |                    10.22 | PROPOSED |
|              15 | SHORT-2026-000028 | SKU-000099 | LOC-005       | 2026W23            |           1175 | INBOUND_CANCELLED      | NEW_PO            | SUP-0036      |          100    |       882.18 |               -116063    | PROPOSED |

Shortages needing review (missing lead time): **7**

## Supplier - capacity exceedances and constrained supplier-weeks

| supplier_id   | product_family   | week_start_date   |   committed_qty |   capacity_qty |   utilisation_pct |
|:--------------|:-----------------|:------------------|----------------:|---------------:|------------------:|
| SUP-0001      | FAM-01           | 2026-02-02        |             402 |            321 |           125.234 |
| SUP-0001      | FAM-02           | 2026-02-02        |             948 |            758 |           125.066 |
| SUP-0001      | FAM-11           | 2026-03-09        |            2742 |           2193 |           125.034 |
| SUP-0002      | FAM-02           | 2026-02-16        |            3360 |           2688 |           125     |

Supplier-weeks at >= 90 % utilisation: **16** of 838

## Carrier / warehouse operator - delayed inbound and receipts

| po_id          | supplier_id   | sku_id     | ship_to_location_id   | carrier_id   | promised_date   | eta_date   | status     |
|:---------------|:--------------|:-----------|:----------------------|:-------------|:----------------|:-----------|:-----------|
| PO-2026-000108 | SUP-0049      | SKU-000149 | LOC-002               | CAR-02       | 2025-12-29      | 2025-12-29 | IN_TRANSIT |
| PO-2026-000106 | SUP-0032      | SKU-000053 | LOC-010               | CAR-01       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-000102 | SUP-0009      | SKU-000274 | LOC-004               | CAR-03       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-000107 | SUP-0036      | SKU-000099 | LOC-007               | CAR-03       | 2026-01-01      | 2026-01-01 | IN_TRANSIT |
| PO-2026-000113 | SUP-0008      | SKU-000255 | LOC-003               | CAR-02       | 2026-01-02      | 2026-01-02 | IN_TRANSIT |
| PO-2026-000096 | SUP-0047      | SKU-000227 | LOC-008               | CAR-02       | 2026-01-02      | 2026-01-02 | IN_TRANSIT |
| PO-2026-000087 | SUP-0007      | SKU-000045 | LOC-003               | CAR-01       | 2026-01-06      | 2026-01-06 | IN_TRANSIT |
| PO-2026-000100 | SUP-0018      | SKU-000288 | LOC-003               | CAR-04       | 2026-01-06      | 2026-01-06 | IN_TRANSIT |
| PO-2026-000036 | SUP-0034      | SKU-000150 | LOC-008               | CAR-06       | 2026-01-07      | 2026-01-07 | IN_TRANSIT |
| PO-2026-000051 | SUP-0006      | SKU-000252 | LOC-002               | CAR-05       | 2026-01-07      | 2026-01-07 | IN_TRANSIT |
| PO-2026-000088 | SUP-0010      | SKU-000203 | LOC-005               | CAR-04       | 2026-01-07      | 2026-01-07 | IN_TRANSIT |
| PO-2026-000104 | SUP-0002      | SKU-000261 | LOC-008               | CAR-01       | 2025-12-29      | 2026-01-07 | DELAYED    |
| PO-2026-000040 | SUP-0011      | SKU-000191 | LOC-009               | CAR-05       | 2026-01-10      | 2026-01-10 | IN_TRANSIT |
| PO-2026-000043 | SUP-0011      | SKU-000060 | LOC-008               | CAR-06       | 2026-01-12      | 2026-01-12 | IN_TRANSIT |
| PO-2026-000048 | SUP-0001      | SKU-000175 | LOC-010               | CAR-05       | 2026-01-13      | 2026-01-13 | IN_TRANSIT |

Delayed shipments: **19**; receipts posted: **60**

## Logistics analyst - transport delays and lead-time exceptions

| reason_code     |   count |   mean |   max |
|:----------------|--------:|-------:|------:|
| BREAKDOWN       |       3 |   11   |    21 |
| CUSTOMS         |       5 |   14.6 |    32 |
| DOCUMENTATION   |       5 |   13.4 |    27 |
| PORT_CONGESTION |       5 |   17.6 |    27 |
| WEATHER         |       1 |   18   |    18 |

| record_id           | related_record_ids                                    | detail                                                                                            |
|:--------------------|:------------------------------------------------------|:--------------------------------------------------------------------------------------------------|
| SUP-0031|SKU-000008 | SHORT-2026-000002|SHORT-2026-000003|SHORT-2026-000004 | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0042|SKU-000008 | SHORT-2026-000002|SHORT-2026-000003|SHORT-2026-000004 | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0014|SKU-000010 | SHORT-2026-000005|SHORT-2026-000006                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0043|SKU-000010 | SHORT-2026-000005|SHORT-2026-000006                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0015|SKU-000027 | SHORT-2026-000007                                     | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0018|SKU-000030 | SHORT-2026-000008                                     | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |

## Operations manager - KPIs and approvals

| kpi                                |            value |
|:-----------------------------------|-----------------:|
| shortages                          |     92           |
| value at risk (USD)                | 746371           |
| mean recommended fill rate %       |     97.52        |
| recommended incremental cost (USD) |  13921.4         |
| do-nothing backorder cost (USD)    |      1.25552e+06 |

Recommended options requiring OPS_MANAGER approval (spend above threshold):

| shortage_id       | option_type   | supplier_id   |   qty |   total_cost |
|:------------------|:--------------|:--------------|------:|-------------:|
| SHORT-2026-000013 | NEW_PO        | SUP-0007      |  2058 |      1766.93 |
| SHORT-2026-000028 | NEW_PO        | SUP-0036      |  1200 |       882.18 |
| SHORT-2026-000029 | NEW_PO        | SUP-0036      |  1920 |      1207.91 |
| SHORT-2026-000030 | NEW_PO        | SUP-0036      |  1728 |      1207.7  |
| SHORT-2026-000088 | NEW_PO        | SUP-0009      |  1296 |       914.96 |

### Data-quality exceptions raised by the engine

| issue_type                 |   count |
|:---------------------------|--------:|
| INBOUND_DOUBLE_COUNT       |       6 |
| SHORTAGE_MISSING_LEAD_TIME |       6 |
| UOM_MISMATCH               |       4 |
| SUPPLIER_CAPACITY_EXCEEDED |       4 |
| SUBSTITUTE_NOT_APPROVED    |       4 |


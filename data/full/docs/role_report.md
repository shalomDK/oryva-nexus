# Role-based decision & exception report

Generated from the exported tables only. Each section is what that actor needs to act.

## Planner - top 15 shortages with the recommended mitigation

|   priority_rank | shortage_id       | sku_id     | location_id   | first_short_week   |   shortage_qty | primary_cause_code     | option_type       | supplier_id   |   fill_rate_pct |   total_cost |   cost_delta_vs_baseline | status   |
|----------------:|:------------------|:-----------|:--------------|:-------------------|---------------:|:-----------------------|:------------------|:--------------|----------------:|-------------:|-------------------------:|:---------|
|               1 | SHORT-2026-001056 | SKU-002028 | LOC-029       | 2026W03            |           1695 | INBOUND_CANCELLED      | NEW_PO            | SUP-0055      |          100    |      2588.72 |               -692226    | PROPOSED |
|               2 | SHORT-2026-000710 | SKU-001320 | LOC-042       | 2026W03            |           2330 | INBOUND_CANCELLED      | ALT_SUPPLIER_PO   | SUP-0360      |           98    |     19737.9  |               -672738    | PROPOSED |
|               3 | SHORT-2026-001039 | SKU-002012 | LOC-024       | 2026W01            |            279 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |           99.28 |        76.66 |                  -746.95 | PROPOSED |
|               4 | SHORT-2026-000491 | SKU-000891 | LOC-012       | 2026W01            |             67 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0394      |          100    |       415.63 |                    80.95 | PROPOSED |
|               5 | SHORT-2026-001193 | SKU-002208 | LOC-018       | 2026W04            |           1369 | INBOUND_CANCELLED      | NEW_PO            | SUP-0225      |          100    |      2433.81 |               -599149    | PROPOSED |
|               6 | SHORT-2026-000691 | SKU-001291 | LOC-042       | 2026W01            |            293 | INBOUND_LATE_TRANSPORT | ALT_SUPPLIER_PO   | SUP-0457      |           66.67 |       379.63 |                 -8771.11 | PROPOSED |
|               7 | SHORT-2026-000549 | SKU-001010 | LOC-036       | 2026W02            |            299 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |           77.26 |       387.25 |                 -3622.7  | PROPOSED |
|               8 | SHORT-2026-000061 | SKU-000108 | LOC-024       | 2026W02            |            116 | SUPPLIER_CAPACITY      | EXPEDITE_PO       | SUP-0470      |          100    |       757.43 |                  -546.04 | PROPOSED |
|               9 | SHORT-2026-001411 | SKU-002651 | LOC-020       | 2026W02            |            325 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |           93.85 |       128.28 |                  -965.28 | PROPOSED |
|              10 | SHORT-2026-000263 | SKU-000455 | LOC-039       | 2026W02            |            375 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |           85.07 |       152.98 |                 -4642.52 | PROPOSED |
|              11 | SHORT-2026-001019 | SKU-001968 | LOC-029       | 2026W03            |           3101 | INBOUND_CANCELLED      | NEW_PO            | SUP-0084      |          100    |       536.31 |                -95182.9  | PROPOSED |
|              12 | SHORT-2026-000330 | SKU-000560 | LOC-024       | 2026W02            |            194 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0011      |           40    |       613.82 |                 -3273.16 | PROPOSED |
|              13 | SHORT-2026-000539 | SKU-001006 | LOC-029       | 2026W02            |             87 | INBOUND_LATE_TRANSPORT | EXPEDITE_PO       | SUP-0025      |           66.67 |       477.33 |                  -883.84 | PROPOSED |
|              14 | SHORT-2026-000354 | SKU-000622 | LOC-030       | 2026W02            |             95 | INBOUND_LATE_TRANSPORT | LOCATION_TRANSFER |               |          100    |        70.2  |                  -865.74 | PROPOSED |
|              15 | SHORT-2026-000774 | SKU-001507 | LOC-021       | 2026W02            |            103 | SUPPLIER_CAPACITY      | LOCATION_TRANSFER |               |          100    |        41.76 |                  -403.69 | PROPOSED |

Shortages needing review (missing lead time): **43**

## Supplier - capacity exceedances and constrained supplier-weeks

| supplier_id   | product_family   | week_start_date   |   committed_qty |   capacity_qty |   utilisation_pct |
|:--------------|:-----------------|:------------------|----------------:|---------------:|------------------:|
| SUP-0001      | FAM-01           | 2026-01-12        |            1080 |            864 |           125     |
| SUP-0001      | FAM-03           | 2026-01-19        |            1968 |           1574 |           125.032 |
| SUP-0002      | FAM-02           | 2026-08-10        |            2784 |           2227 |           125.011 |
| SUP-0002      | FAM-04           | 2026-01-05        |            3858 |           3086 |           125.016 |
| SUP-0002      | FAM-11           | 2025-12-29        |            1416 |           1132 |           125.088 |
| SUP-0003      | FAM-03           | 2026-01-12        |            1614 |           1291 |           125.019 |
| SUP-0003      | FAM-12           | 2025-12-29        |            5640 |           4512 |           125     |
| SUP-0004      | FAM-04           | 2026-01-12        |            1200 |            960 |           125     |
| SUP-0006      | FAM-06           | 2026-01-05        |            3469 |           2775 |           125.009 |
| SUP-0006      | FAM-07           | 2026-04-27        |            2118 |           1694 |           125.029 |
| SUP-0006      | FAM-10           | 2026-02-02        |            4590 |           3672 |           125     |
| SUP-0007      | FAM-07           | 2026-01-05        |            4080 |           3264 |           125     |
| SUP-0008      | FAM-08           | 2025-12-29        |            5952 |           4761 |           125.016 |
| SUP-0009      | FAM-05           | 2025-12-29        |           14052 |          11241 |           125.007 |
| SUP-0009      | FAM-06           | 2025-12-29        |             672 |            537 |           125.14  |

Supplier-weeks at >= 90 % utilisation: **134** of 8266

## Carrier / warehouse operator - delayed inbound and receipts

| po_id          | supplier_id   | sku_id     | ship_to_location_id   | carrier_id   | promised_date   | eta_date   | status     |
|:---------------|:--------------|:-----------|:----------------------|:-------------|:----------------|:-----------|:-----------|
| PO-2026-000485 | SUP-0449      | SKU-000697 | LOC-022               | CAR-05       | 2025-12-29      | 2025-12-29 | IN_TRANSIT |
| PO-2026-000863 | SUP-0276      | SKU-002672 | LOC-031               | CAR-04       | 2025-12-29      | 2025-12-29 | IN_TRANSIT |
| PO-2026-000868 | SUP-0093      | SKU-000170 | LOC-039               | CAR-02       | 2025-12-30      | 2025-12-30 | IN_TRANSIT |
| PO-2026-001224 | SUP-0141      | SKU-000053 | LOC-019               | CAR-02       | 2025-12-30      | 2025-12-30 | IN_TRANSIT |
| PO-2026-000773 | SUP-0315      | SKU-002651 | LOC-035               | CAR-03       | 2025-12-30      | 2025-12-30 | IN_TRANSIT |
| PO-2026-001116 | SUP-0161      | SKU-002083 | LOC-031               | CAR-02       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-001051 | SUP-0425      | SKU-002796 | LOC-019               | CAR-01       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-001139 | SUP-0235      | SKU-000756 | LOC-038               | CAR-01       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-001179 | SUP-0425      | SKU-000535 | LOC-031               | CAR-02       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-000413 | SUP-0154      | SKU-001328 | LOC-038               | CAR-06       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-000247 | SUP-0152      | SKU-002867 | LOC-022               | CAR-06       | 2025-12-31      | 2025-12-31 | IN_TRANSIT |
| PO-2026-000919 | SUP-0026      | SKU-002232 | LOC-039               | CAR-07       | 2026-01-01      | 2026-01-01 | IN_TRANSIT |
| PO-2026-000757 | SUP-0115      | SKU-000016 | LOC-024               | CAR-04       | 2026-01-01      | 2026-01-01 | IN_TRANSIT |
| PO-2026-000806 | SUP-0126      | SKU-001146 | LOC-001               | CAR-03       | 2026-01-01      | 2026-01-01 | IN_TRANSIT |
| PO-2026-000942 | SUP-0282      | SKU-001506 | LOC-042               | CAR-03       | 2026-01-01      | 2026-01-01 | IN_TRANSIT |

Delayed shipments: **178**; receipts posted: **600**

## Logistics analyst - transport delays and lead-time exceptions

| reason_code     |   count |   mean |   max |
|:----------------|--------:|-------:|------:|
| BREAKDOWN       |      39 |   17   |    35 |
| CUSTOMS         |      33 |   16   |    34 |
| DOCUMENTATION   |      34 |   18.8 |    35 |
| PORT_CONGESTION |      29 |   17.7 |    33 |
| WEATHER         |      43 |   16   |    35 |

| record_id           | related_record_ids                  | detail                                                                                            |
|:--------------------|:------------------------------------|:--------------------------------------------------------------------------------------------------|
| SUP-0104|SKU-000008 | SHORT-2026-000001                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0156|SKU-000008 | SHORT-2026-000001                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0115|SKU-000016 | SHORT-2026-000002                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0158|SKU-000016 | SHORT-2026-000002                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0250|SKU-000022 | SHORT-2026-000003                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0242|SKU-000023 | SHORT-2026-000004                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0127|SKU-000033 | SHORT-2026-000022                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0345|SKU-000033 | SHORT-2026-000022                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0470|SKU-000033 | SHORT-2026-000022                   | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |
| SUP-0091|SKU-000041 | SHORT-2026-000023|SHORT-2026-000024 | shortage exists but no lead time for this supplier/SKU: mitigation blocked, shortage needs review |

## Operations manager - KPIs and approvals

| kpi                                |            value |
|:-----------------------------------|-----------------:|
| shortages                          |   1600           |
| value at risk (USD)                |      1.80446e+07 |
| mean recommended fill rate %       |     97.74        |
| recommended incremental cost (USD) | 391296           |
| do-nothing backorder cost (USD)    |      3.03319e+07 |

Recommended options requiring OPS_MANAGER approval (spend above threshold):

| shortage_id       | option_type     | supplier_id   |   qty |   total_cost |
|:------------------|:----------------|:--------------|------:|-------------:|
| SHORT-2026-000089 | NEW_PO          | SUP-0421      |   960 |      3588.96 |
| SHORT-2026-000101 | NEW_PO          | SUP-0138      |  4428 |       631.42 |
| SHORT-2026-000109 | ALT_SUPPLIER_PO | SUP-0080      |  1422 |       778.47 |
| SHORT-2026-000110 | ALT_SUPPLIER_PO | SUP-0080      |  2142 |      1156.03 |
| SHORT-2026-000111 | ALT_SUPPLIER_PO | SUP-0080      |  3072 |      1637.18 |
| SHORT-2026-000112 | ALT_SUPPLIER_PO | SUP-0080      |  4074 |      2162.63 |
| SHORT-2026-000190 | NEW_PO          | SUP-0047      |  2773 |       706.01 |
| SHORT-2026-000191 | ALT_SUPPLIER_PO | SUP-0143      |  5400 |      1283.62 |
| SHORT-2026-000201 | NEW_PO          | SUP-0440      |  5844 |      1209.5  |
| SHORT-2026-000215 | ALT_SUPPLIER_PO | SUP-0077      |  2370 |      1238.14 |

### Data-quality exceptions raised by the engine

| issue_type                 |   count |
|:---------------------------|--------:|
| SHORTAGE_MISSING_LEAD_TIME |      60 |
| INBOUND_DOUBLE_COUNT       |      45 |
| UOM_MISMATCH               |      30 |
| SUPPLIER_CAPACITY_EXCEEDED |      30 |
| SUBSTITUTE_NOT_APPROVED    |      30 |


# 2D Drawing Index

**Field definitions:**
- `Shape`: primary bounding-volume shape (`CUBE` or `CYL`).
- Axis columns record the physical 3D bounding axis, not the orientation of a drawing view.
- For `CUBE`, standard axes are Thk=`Z`, W=`X`, and L=`Y`.
- For `CYL`, only the length axis is recorded; the standard is L=`X`.
- For dual-dimensioned drawings, record only the primary unbracketed values and set `Units` to that primary system; omit bracketed converted values.
- `Orthographic Projection` defaults to `3rd Angle Projection` unless explicitly identified otherwise.
- `Notes` is reserved for genuine bounding-dimension exceptions or calculations.
- `Measured From` applies only to chained dimensions. `Part Edge` means zero is at an
  outside edge of the part, which is normal. `In-Between Edges` means zero sits between
  the part's two edges instead of at one edge, so the bounding dimension is the sum of
  two dimensions on opposite sides of zero.

## JRE Drawings

| File | Part No | Shape | Units | Dia | Thk | Thk Axis | W | W Axis | L | L Axis | Material | Orthographic Projection | Notes | Measured From |
|------|---------|-------|-------|-----|-----|----------|---|--------|---|--------|----------|-------------------------|-------|---------------|
| 90-100005-A.pdf | 90-100005 | CYL | IN | 0.1250 |  |  |  |  | 2.8821 | X | AISI M2 (HSS) | 3rd Angle Projection |  |  |
| 90-100009-A.pdf | 90-100009 | CYL | IN | 1.609 |  |  |  |  | 0.750 | X | AISI 4140 | 3rd Angle Projection |  |  |
| 90-100012-B.pdf | 90-100012 | CYL | IN | 1.1240 |  |  |  |  | 6.50 + 1.00 = 7.50 | X | AISI 4140 HR Q&T | 3rd Angle Projection |  | In-Between Edges |
| 90-100013-A.pdf | 90-100013 | CYL | IN | 1.5000 |  |  |  |  | 3.83 + 1.13 = 4.96 | X | ADS 6061-T6 | 3rd Angle Projection |  | In-Between Edges |
| 90-100022-A.pdf | 90-100022 | CYL | IN | 0.1870 |  |  |  |  | 7.530 | X | AISI 4140 CR | 3rd Angle Projection |  |  |
| 17872-006.pdf | 17872-006 | CUBE | IN |  | 2 | Z | 29.62 | X | 33.00 | Y |  | 3rd Angle Projection |  |  |
| 18178-002.pdf | 18178-002 | CUBE | IN |  | 2 | Z | 32 | X | 10 | Y |  | 3rd Angle Projection |  |  |
| 18202-001.pdf | 18202-001 | CUBE | IN |  | 1.75 | Z | 26.00 | X | 19.00 | Y |  | 3rd Angle Projection |  |  |
| 18592-002.pdf | 18592-002 | CUBE | IN |  | 1.25 | Z | 14.00 | X | 16.00 | Y |  | 3rd Angle Projection |  |  |
| 18592-034.pdf | 18592-034 | CYL | IN | 4.00 |  |  |  |  | 6.72 | Y |  | 3rd Angle Projection |  |  |
| 19206-016.pdf | 19206-016 | CUBE | IN |  | 2.000 | Z | 14.000 | X | 14.000 | Y |  | 3rd Angle Projection |  |  |
| 200473-001.pdf | 200473-001 | CUBE | MM |  | 50.8 | Z | 1828.8 | X | 914.4 | Y |  | 3rd Angle Projection |  |  |
| 200473-002.pdf | 200473-002 | CUBE | MM |  | 12.7 | Z | 711.2 | X | 304.8 | Y |  | 3rd Angle Projection |  |  |
| 200473-003.pdf | 200473-003 | CUBE | MM |  | 12.7 | Z | 685.80 | X | 241.3 | Y |  | 3rd Angle Projection |  |  |
| 200473-004.pdf | 200473-004 | CUBE | MM |  | 12.7 | Z | 101.6 | X | 152.4 | Y |  | 3rd Angle Projection |  |  |
| 200473-005.pdf | 200473-005 | CUBE | MM |  | 38.1 | Z | 69.9 | X | 69.9 | Y |  | 3rd Angle Projection |  |  |
| 200473-006.pdf | 200473-006 | CYL | MM | 25.4 |  |  |  |  | 53.98 | Y |  | 3rd Angle Projection |  |  |
| 200473-007.pdf | 200473-007 | CUBE | MM |  | 50.8 | Z | 63.5 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-008.pdf | 200473-008 | CUBE | MM |  | 101.6 | Z | 63.5 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-009.pdf | 200473-009 | CUBE | MM |  | 50.8 | Z | 63.5 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-010.pdf | 200473-010 | CUBE | MM |  | 50.8 | Z | 63.5 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-011.pdf | 200473-011 | CUBE | MM |  | 50.8 | Z | 63.5 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-012.pdf | 200473-012 | CUBE | MM |  | 50.8 | Z | 76.2 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200473-013.pdf | 200473-013 | CUBE | MM |  | 50.8 | Z | 76.2 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 200944.pdf | 200944 | CYL | MM | 10.0 |  |  |  |  | 75.0 | X |  | 3rd Angle Projection |  |  |
| 200947.pdf | 200947 | CYL | MM | 12.0 |  |  |  |  | 145.0 | X |  | 3rd Angle Projection |  |  |
| 200951.pdf | 200951 | CUBE | MM |  | 34.29 + 6.35 = 40.64 | Z | 91.0 | X | 72.91 | Y |  | 3rd Angle Projection |  | In-Between Edges |
| 201007.pdf | 201007 | CYL | MM | 11.00 |  |  |  |  | 90.0 | X |  | 3rd Angle Projection |  |  |
| 201011.pdf | 201011 | CYL | MM | 8.000 |  |  |  |  | 90.0 | X |  | 3rd Angle Projection |  |  |
| 201057-001.pdf | 201057-001 | CUBE | MM |  | 19.1 | Z | 304.8 | X | 304.8 | Y |  | 3rd Angle Projection |  |  |
| 201057-002.pdf | 201057-002 | CUBE | MM |  | 12.7 | Z | 276.2 | X | 304.8 | Y |  | 3rd Angle Projection |  |  |
| 201057-003.pdf | 201057-003 | CYL | MM | 105.50 |  |  |  |  | 50.8 | Y |  | 3rd Angle Projection |  |  |
| 201057-004.pdf | 201057-004 | CYL | MM | 25.4 |  |  |  |  | 50.8 | X |  | 3rd Angle Projection |  |  |
| 201057-006.pdf | 201057-006 | CYL | MM | 15.9 |  |  |  |  | 75.0 | X |  | 3rd Angle Projection |  |  |
| 201258-001.pdf | 201258-001 | CUBE | MM |  | 19.1 | Z | 330.2 | X | 254.0 | Y |  | 3rd Angle Projection |  |  |
| 201258-002.pdf | 201258-002 | CYL | MM | 63.50 |  |  |  |  | 1.52 | X |  | 3rd Angle Projection |  |  |
| 201258-003.pdf | 201258-003 | CUBE | MM |  | 12.7 | Z | 44.4 | X | 15.7 | Y |  | 3rd Angle Projection |  |  |
| 201258-004.pdf | 201258-004 | CYL | MM | 34.9 |  |  |  |  | 146.1 | X |  | 3rd Angle Projection |  |  |
| 201258-005.pdf | 201258-005 | CYL | MM | 38.1 |  |  |  |  | 76.20 | X |  | 3rd Angle Projection |  |  |
| 201258-006.pdf | 201258-006 | CYL | MM | 6.350 |  |  |  |  | 131.24 | X |  | 3rd Angle Projection |  |  |
| 201258-008.pdf | 201258-008 | CUBE | MM |  | 38.10 | Z | 168.28 | X | 99.9 | Y |  | 3rd Angle Projection |  |  |
| 201258-009.pdf | 201258-009 | CUBE | MM |  | 76.2 | Z | 127.0 | X | 157.2 | Y |  | 3rd Angle Projection |  |  |
| 201258-010.pdf | 201258-010 | CYL | MM | 12.700 |  |  |  |  | 127.0 | X |  | 3rd Angle Projection | Diameter callout formatting defect: print shows Ø.5000 only; intended dual-dimension callout is Ø12.700 [.5000]. |  |
| 201258-011.pdf | 201258-011 | CYL | MM | 57.2 |  |  |  |  | 34.9 | Y |  | 3rd Angle Projection |  |  |
| 201258-012.pdf | 201258-012 | CYL | MM | 90.4 |  |  |  |  | 57.150 | Y |  | 3rd Angle Projection |  |  |
| 201258-013.pdf | 201258-013 | CYL | MM | 108.0 |  |  |  |  | 14.9 | Y |  | 3rd Angle Projection |  |  |
| 201258-014.pdf | 201258-014 | CYL | MM | 88.9 |  |  |  |  | 12.7 | Y |  | 3rd Angle Projection |  |  |
| 201258-015.pdf | 201258-015 | CYL | MM | 38.1 |  |  |  |  | 127.0 | X |  | 3rd Angle Projection |  |  |
| 201258-016.pdf | 201258-016 | CYL | MM | 11.1 |  |  |  |  | 1.5 | X |  | 3rd Angle Projection |  |  |
| 201258-017.pdf | 201258-017 | CYL | MM | 25.4 |  |  |  |  | 127.0 | X |  | 3rd Angle Projection |  |  |
| 201258-018.pdf | 201258-018 | CYL | MM | 69.9 |  |  |  |  | 12.70 | Y |  | 3rd Angle Projection |  |  |
| 201258-019.pdf | 201258-019 | CYL | MM | 69.8 |  |  |  |  | 148.65 | X |  | 3rd Angle Projection |  |  |
| 201258-020.pdf | 201258-020 | CUBE | MM |  | 28.6 | Z | 25.4 | X | 85.0 | Y |  | 3rd Angle Projection |  |  |
| 201258-021.pdf | 201258-021 | CUBE | MM |  | 28.6 | Z | 34.93 | X | 68.0 | Y |  | 3rd Angle Projection |  |  |
| 201258-022.pdf | 201258-022 | CUBE | MM |  | 47.6 | Z | 46.0 | X | 54.0 | Y |  | 3rd Angle Projection |  |  |
| 201258-023.pdf | 201258-023 | CYL | MM | 38.00 |  |  |  |  | 50.8 | Y |  | 3rd Angle Projection |  |  |
| 201508.pdf | 201508 | CUBE | MM |  | 25.4 | Z | 58.4 | X | 31.8 | Y | Delrin | 3rd Angle Projection |  |  |
| 201513.pdf | 201513 | CUBE | MM |  | 75.8 | Z | 85.0 | X | 64.8 | Y | AISI A2 | 3rd Angle Projection |  |  |
| 201516.pdf | 201516 | CUBE | MM |  | 25.4 | Z | 62.7 | X | 15.6 + 22.5 = 38.1 | Y |  | 3rd Angle Projection | Similar to example 2B on [machinable.ai/research.html](https://machinable.ai/research.html); drawing does not provide an explicit overall length dimension; length calculated by summing two consecutive Y-axis dimensions (15.6 + 22.5); Y-axis origin is an internal datum, not an external part edge. | In-Between Edges |
| 201533-010.pdf | 201533-010 | CYL | MM | 92.000 |  |  |  |  | 16.000 | Y |  | 3rd Angle Projection |  |  |
| 201533-011.pdf | 201533-011 | CUBE | MM |  | 31.8 | Z | 48.9 | X | 117.3 | Y |  | 3rd Angle Projection |  |  |
| 201533-020.pdf | 201533-020 | CUBE | MM |  | 12.700 | Z | 215.9 | X | 184.2 | Y | MIC-6 Cast Aluminum | 3rd Angle Projection |  |  |
| 201548-003.pdf | 201548-003 | CYL | MM | 15.9 |  |  |  |  | 73.76 | X |  | 3rd Angle Projection |  |  |
| 201548-006.pdf | 201548-006 | CYL | MM | 15.9 |  |  |  |  | 97.23 | X |  | 3rd Angle Projection |  |  |
| 201548-007.pdf | 201548-007 | CUBE | MM |  | 19.1 | Z | 114.3 | X | 139.7 | Y | 1018 | 3rd Angle Projection |  |  |
| 201548-008.pdf | 201548-008 | CUBE | MM |  | 63.500 | Z | 127.0 | X | 311.2 | Y | 1018 | 3rd Angle Projection |  |  |
| 201548-009.pdf | 201548-009 | CYL | MM | 38.1 |  |  |  |  | 203.2 | X | 1018 | 3rd Angle Projection |  |  |
| 201548-013.pdf | 201548-013 | CUBE | MM |  | 25.400 | Z | 228.600 | X | 241.300 | Y | 4140 Alloy Steel | 3rd Angle Projection |  |  |
| 201548-014.pdf | 201548-014 | CUBE | MM |  | 25.4 | Z | 228.6 | X | 123.8 | Y |  | 3rd Angle Projection |  |  |
| 201548-016.pdf | 201548-016 | CYL | MM | 8.310 |  |  |  |  | 42.3 | X |  | 3rd Angle Projection |  |  |
| 201548-018.pdf | 201548-018 | CUBE | MM |  | 6.10 | Z | 123.8 | X | 114.3 | Y |  | 3rd Angle Projection |  |  |
| 201548-019.pdf | 201548-019 | CYL | MM | 8.000 |  |  |  |  | 50.8 | X | Drill Rod Stk | 3rd Angle Projection |  |  |
| 201548-025.pdf | 201548-025 | CYL | MM | 8.000 |  |  |  |  | 92.1 | X |  | 3rd Angle Projection |  |  |
| 201548-026.pdf | 201548-026 | CYL | MM | 8.000 |  |  |  |  | 114.3 | X |  | 3rd Angle Projection |  |  |
| 201548-028.pdf | 201548-028 | CYL | MM | 7.94 |  |  |  |  | 64.29 | X |  | 3rd Angle Projection |  |  |
| 201548-029.pdf | 201548-029 | CYL | MM | 8.000 |  |  |  |  | 142.9 | X |  | 3rd Angle Projection |  |  |
| 201548-030.pdf | 201548-030 | CYL | MM | 25.400 |  |  |  |  | 88.90 | X |  | 3rd Angle Projection |  |  |
| 201551-001.pdf | 201551-001 | CUBE | MM |  | 38.1 | Z | 355.6 | X | 254.0 | Y | 1020 | 3rd Angle Projection |  |  |
| 201551-002.pdf | 201551-002 | CUBE | MM |  | 47.63 | Z | 203.2 | X | 152.4 | Y |  | 3rd Angle Projection |  |  |
| 201551-003.pdf | 201551-003 | CUBE | MM |  | 69.85 | Z | 81.0 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 201551-004.pdf | 201551-004 | CUBE | MM |  | 69.85 | Z | 81.0 | X | 101.6 | Y |  | 3rd Angle Projection |  |  |
| 201551-005.pdf | 201551-005 | CUBE | MM |  | 63.5 | Z | 127.0 | X | 330.2 | Y |  | 3rd Angle Projection |  |  |
| 201551-006.pdf | 201551-006 | CUBE | MM |  | 19.1 | Z | 101.6 | X | 139.7 | Y |  | 3rd Angle Projection |  |  |
| 201551-007.pdf | 201551-007 | CYL | MM | 32.23 |  |  |  |  | 57.2 | X |  | 3rd Angle Projection |  |  |
| 201551-008.pdf | 201551-008 | CUBE | MM |  | 25.4 | Z | 44.5 | X | 50.8 | Y |  | 3rd Angle Projection |  |  |
| 201551-009.pdf | 201551-009 | CUBE | MM |  | 31.8 | Z | 177.8 | X | 44.5 | Y |  | 3rd Angle Projection |  |  |
| 201551-010.pdf | 201551-010 | CUBE | MM |  | 22.2 | Z | 59.7 | X | 106.4 | Y |  | 3rd Angle Projection |  |  |
| 201551-011.pdf | 201551-011 | CUBE | MM |  | 19.050 | Z | 177.8 | X | 108.0 | Y |  | 3rd Angle Projection |  |  |
| 201551-012.pdf | 201551-012 | CUBE | MM |  | 25.4 | Z | 50.8 | X | 44.5 | Y |  | 3rd Angle Projection |  |  |
| 201551-013.pdf | 201551-013 | CYL | MM | 38.1 |  |  |  |  | 50.8 | X |  | 3rd Angle Projection |  |  |
| 201551-014.pdf | 201551-014 | CYL | MM | 19.1 |  |  |  |  | 19.1 | X |  | 3rd Angle Projection |  |  |
| 201551-015.pdf | 201551-015 | CUBE | MM |  | 22.2 | Z | 59.7 | X | 106.4 | Y |  | 3rd Angle Projection |  |  |
| 201551-016.pdf | 201551-016 | CUBE | MM |  | 25.4 | Z | 63.5 | X | 19.1 | Y |  | 3rd Angle Projection |  |  |
| 201551-017.pdf | 201551-017 | CUBE | MM |  | 100.5 | Z | 57.2 | X | 114.3 | Y |  | 3rd Angle Projection |  |  |
| 201551-018.pdf | 201551-018 | CUBE | MM |  | 15.9 | Z | 76.2 | X | 63.5 | Y |  | 3rd Angle Projection |  |  |
| 201551-019.pdf | 201551-019 | CYL | MM | 31.75 |  |  |  |  | 47.36 | X |  | 3rd Angle Projection |  |  |
| 201551-020.pdf | 201551-020 | CYL | MM | 83.570 |  |  |  |  | 6.615 | X |  | 3rd Angle Projection |  |  |
| 201551-021.pdf | 201551-021 | CYL | MM | 83.57 |  |  |  |  | 4.060 | X |  | 3rd Angle Projection |  |  |
| 201551-022.pdf | 201551-022 | CYL | MM | 83.570 |  |  |  |  | 3.640 | X |  | 3rd Angle Projection |  |  |
| 201551-023.pdf | 201551-023 | CYL | MM | 83.570 |  |  |  |  | 2.485 | X |  | 3rd Angle Projection |  |  |
| 201551-024.pdf | 201551-024 | CYL | MM | 83.570 |  |  |  |  | 6.4 | X |  | 3rd Angle Projection |  |  |
| 201551-025.pdf | 201551-025 | CYL | MM | 83.57 |  |  |  |  | 33.750 | Y |  | 3rd Angle Projection |  |  |
| 201552-001.pdf | 201552-001 | CUBE | MM |  | 19.1 | Z | 254.0 | X | 177.8 | Y |  | 3rd Angle Projection |  |  |
| 201552-002.pdf | 201552-002 | CUBE | MM |  | 31.75 | Z | 152.4 | X | 135.46 | Y |  | 3rd Angle Projection |  |  |
| 201552-003.pdf | 201552-003 | CUBE | MM |  | 6.4 | Z | 63.5 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-004.pdf | 201552-004 | CUBE | MM |  | 6.4 | Z | 71.7 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-005.pdf | 201552-005 | CUBE | MM |  | 6.4 | Z | 69.9 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-006.pdf | 201552-006 | CUBE | MM |  | 4.0 | Z | 23.0 | X | 10.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-007.pdf | 201552-007 | CUBE | MM |  | 4.0 | Z | 23.0 | X | 10.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-008.pdf | 201552-008 | CUBE | MM |  | 4.0 | Z | 23.0 | X | 10.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-009.pdf | 201552-009 | CUBE | MM |  | 6.4 | Z | 34.0 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-010.pdf | 201552-010 | CUBE | MM |  | 8.0 | Z | 38.1 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-012.pdf | 201552-012 | CUBE | MM |  | 6.0 | Z | 25.0 | X | 20.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-013.pdf | 201552-013 | CYL | MM | 10.00 |  |  |  |  | 80.50 | X |  | 3rd Angle Projection |  |  |
| 201552-014.pdf | 201552-014 | CUBE | MM |  | 4.0 | Z | 15.0 | X | 10.0 | Y |  | 3rd Angle Projection |  |  |
| 201552-015.pdf | 201552-015 | CUBE | MM |  | 19.1 | Z | 40.64 | X | 118.1 | Y |  | 3rd Angle Projection |  |  |
| 201552-016.pdf | 201552-016 | CUBE | MM |  | 19.1 | Z | 40.6 | X | 118.1 | Y |  | 3rd Angle Projection |  |  |
| 201552-017.pdf | 201552-017 | CYL | MM | 83.57 |  |  |  |  | 6.600 | Y |  | 3rd Angle Projection |  |  |
| 201552-018.pdf | 201552-018 | CYL | MM | 83.57 |  |  |  |  | 4.060 | Y |  | 3rd Angle Projection | Min/max calibration master: the two halves are deliberately different sizes. Right (min) side prints 4.060 [.1598]; left (max) side prints 4.06 [.160]. The recorded L is the right side. |  |
| 201552-019.pdf | 201552-019 | CYL | MM | 83.57 |  |  |  |  | 3.640 | Y |  | 3rd Angle Projection |  |  |
| 201552-020.pdf | 201552-020 | CYL | MM | 83.57 |  |  |  |  | 25.4 | Y |  | 3rd Angle Projection |  |  |
| 201553-008.pdf | 201553-008 | CYL | MM | 83.955 |  |  |  |  | 56.900 | Y |  | 3rd Angle Projection |  |  |
| 201581-001.pdf | 201581-001 | CUBE | MM |  | 19.1 | Z | 355.6 | X | 304.8 | Y |  | 3rd Angle Projection |  |  |
| 201581-002.pdf | 201581-002 | CUBE | MM |  | 21.79 | Z | 82.6 | X | 203.2 | Y |  | 3rd Angle Projection |  |  |
| 201581-003.pdf | 201581-003 | CUBE | MM |  | 50.8 | Z | 76.2 | X | 95.3 | Y |  | 3rd Angle Projection |  |  |
| 201581-004.pdf | 201581-004 | CUBE | MM |  | 50.8 | Z | 76.2 | X | 95.3 | Y |  | 3rd Angle Projection |  |  |
| 201581-005.pdf | 201581-005 | CUBE | MM |  | 19.1 | Z | 82.6 | X | 25.4 | Y |  | 3rd Angle Projection |  |  |
| 201581-006.pdf | 201581-006 | CYL | MM | 76.2 |  |  |  |  | 146.1 | X |  | 3rd Angle Projection |  |  |
| 201581-007.pdf | 201581-007 | CYL | MM | 76.2 |  |  |  |  | 120.7 | X |  | 3rd Angle Projection |  |  |
| 201581-008.pdf | 201581-008 | CYL | MM | 9.525 |  |  |  |  | 109.8 | X |  | 3rd Angle Projection |  |  |
| 201581-012.pdf | 201581-012 | CUBE | MM |  | 28.6 | Z | 69.9 | X | 18.8 | Y |  | 3rd Angle Projection |  |  |
| 201581-013.pdf | 201581-013 | CYL | MM | 101.60 |  |  |  |  | 38.1 | Y |  | 3rd Angle Projection |  |  |
| 201581-014.pdf | 201581-014 | CYL | MM | 31.8 |  |  |  |  | 141.3 | X |  | 3rd Angle Projection |  |  |
| 201581-015.pdf | 201581-015 | CUBE | MM |  | 19.1 | Z | 50.8 | X | 38.1 | Y |  | 3rd Angle Projection |  |  |
| 201581-016.pdf | 201581-016 | CYL | MM | 83.570 |  |  |  |  | 56.9 | Y |  | 3rd Angle Projection |  |  |
| 201741-002.pdf | 201741-002 | CUBE | MM |  | 19.050 | Z | 158.8 | X | 203.2 | Y | Mic-6 | 3rd Angle Projection |  |  |
| 201741-003.pdf | 201741-003 | CUBE | MM |  | 63.500 | Z | 127.0 | X | 279.4 | Y | 1018 | 3rd Angle Projection |  |  |
| 201741-004.pdf | 201741-004 | CYL | MM | 25.4 |  |  |  |  | 63.5 | X | 1018 | 3rd Angle Projection |  |  |
| 201741-009.pdf | 201741-009 | CUBE | MM |  | 38.1 | Z | 38.1 | X | 50.8 | Y |  | 3rd Angle Projection |  |  |
| 202985-001.pdf | 202985-001 | CUBE | IN |  | 0.75 | Z | 12.00 | X | 6.00 | Y |  | 3rd Angle Projection |  |  |
| 202997-004.pdf | 202997-004 | CUBE | IN |  | 0.75 | Z | 1.25 | X | 1.50 | Y |  | 3rd Angle Projection |  |  |

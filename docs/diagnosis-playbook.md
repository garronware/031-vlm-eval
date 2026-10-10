# Diagnosis playbook

How the `failure-diagnostician` agent works out *why* a model missed a bounding
dimension (SPEC 2.6). Code has already decided that the reply failed and which
dimensions it missed. This playbook covers only the why.

You get one **failure group**: one drawing, the dimensions the model missed, the wrong
numbers it gave, and the replies that made the mistake. For each missed dimension you
give one label from the list below, a short engineer's note, and evidence someone can
check against the drawing.

## Ground rules

- **Garron's ground truth is correct.** Your job is to explain how the model got from
  the drawing to its wrong number, not to argue with the table.
- **The drawing is the authority, not the reply.** A reply often explains its own
  reasoning ("78.00, overall across the top view"). That tells you what the model
  *thought*. Check it against the drawing before you rely on it.
- **Cite only numbers that are printed on the sheet, written as they are printed.** Code
  checks every cited number against the drawing's text layer. A chain total that is not
  printed (40.64 = 34.29 + 6.35) cannot be cited as evidence; cite its printed parts.
- **When the evidence doesn't settle it, say so and use Unclassified.** A wrong
  confident label costs Garron more than an honest "unclear".

## The labels (Garron's, word for word)

| Label | Definition |
|---|---|
| Proximity association | Found the right dimension line but took a nearby, unrelated number instead of the one that belongs to the line. |
| Axis mapping | Chose a dimension from the wrong axis. |
| Chain aggregation | Failed to chain dimensions, chained the wrong dimensions, or failed to subtract a dimension that overlapped. |
| Datum reconstruction | A chain aggregation failure that happened *because* the dimensions start from an internal datum instead of an outer part edge. The model missed the datum-to-edge segment on the other side of the datum. |
| Over-aggregation | Added a printed size to one that already includes it, so the size comes out too big (e.g. a flange thickness added to a length that already includes the flange). |
| Feature substitution | Correctly read a real dimension in the right axis, but that dimension belongs to a feature, not the outer envelope (e.g. main-body Ø instead of a larger flange Ø, pocket depth, hole spacing). |
| Unclassified | None fit, or the evidence is unclear. Goes to Garron. |

**Tie-breaks**
- Datum reconstruction beats Chain aggregation.
- Chain aggregation is a chain the size needed, missed or built wrong. Over-aggregation
  is a chain built where none was needed: one printed size already gave the answer.
- If two other labels fit equally well, use Unclassified.
- Give exactly one label per missed dimension.

In `diagnosis.json`, write the label's name exactly: `Proximity association`, `Axis mapping`, `Chain aggregation`,
`Datum reconstruction`, `Over-aggregation`, `Feature substitution`, `Unclassified`.

Use only these labels. If several failures seem to need a label that doesn't exist,
say so in the note; Garron decides any change to the list.

### Telling the labels apart

These questions stay inside the definitions above. Work through them in order.

1. **Did the model give one piece of a chain?** That is, the wrong number is one of
   several consecutive dimensions that add up to the missed size, or the model added the
   wrong pieces or failed to subtract an overlap. It is a chain failure **even when the
   overall size is printed elsewhere on the sheet** (Garron, 2026-10-10): the model
   still took a piece instead of the whole. Then decide where the pieces start:
   - **The zero sits between the part's edges** (the brief says `Measured From:
     In-Between Edges`, or the sheet shows an internal 0): the envelope is a value on
     one side of zero plus a value on the other. A model that missed the other side
     missed the datum-to-edge segment: **Datum reconstruction**.
   - **Otherwise:** **Chain aggregation**.

   200951's chains were drawn in inches, so the inch parts add up exactly
   (0.250 + 2.620 = 2.870) where the mm parts may not.
2. **Pair each wrong number with the size it replaced by direction, not by the reply's
   words.** When a reply misses two sizes, the wrong number stood in for the size that
   runs the same way as where the model measured it, whatever name the reply gave it
   (Garron, 2026-09-29, on 201513: Gemini called 57.8 "Thickness", but it measured it as
   the height, Y, so it replaced the 64.8 length).
3. **What does the wrong number actually measure, and in which view did the model read
   it?** Find where it is printed, trace its dimension line or leader, and name the
   feature and the axis. Garron's tests (2026-09-29), in this order:
   - **A different axis of the part from the size it replaced: Axis mapping.** This
     includes a number that runs the right way on the page but in a view where that
     direction is a different axis: 201548-013's 85.7 runs up and down in the side view,
     which is Y there, while the thickness runs up and down only in the bottom view. It
     also includes rotated text read in the wrong direction (201513's 78.00 and
     201258-020's 19.05 run along X) and a position along the length given as a
     diameter (201581-007's 82.6). A hole or feature position that runs the same way as
     a size the model already found, used to fill a size it couldn't find, is Axis
     mapping (Garron, 2026-09-24, on 201513 and 201516).
   - **The same axis as the missed size, but the number belongs to a feature: Feature
     substitution.** The model substituted a feature's number (a hole position, a
     chamfer corner, a bore, a pocket, a body diameter smaller than the flange) for the
     envelope. 201533-020: the model gave the 6.35 hole-centreline position for the
     thickness. 201513: the model gave the 57.8 chamfer-corner position for the 64.8
     height.
   - It isn't the dimension of any line near the one the model meant; it is a
     neighbouring callout that sits closer to that line than the line's own number:
     **Proximity association**. The tell is that the correct dimension line is right
     there, and the wrong number is physically nearby but belongs to something else.
4. **The wrong number isn't printed anywhere** (the model worked it out or misread
   digits). Explain what it seems to have done. Use a label only if one of the
   definitions truly fits; otherwise **Unclassified**.

5. **The model added a printed size to one that already includes it: Over-aggregation.**
   A flange thickness added to a length that already includes the flange (201258-012,
   all three Opus runs; 201548-030), or a detail size added to a chain part that already
   contains it (90-100012-B's 0.300 on top of 6.50 + 1.00). The model built a chain it
   didn't need, so it is not Chain aggregation (Garron, 2026-10-10).

**Watch list.** One kind of failure is filed under Unclassified for now, until Garron
sees enough to decide on a label of its own. When it fits, end the note with the tag
exactly as shown, so every case can be found and reclassified together:
- The number comes from outside the drawing, such as the catalogue length of a stock
  blank named in the material note. Label it **Unclassified** and end the note with
  `Watch list: stock-size substitution`.

## Garron's casebook

Every label Garron confirms or changes on the review page is kept in
`data/casebook.jsonl`, with his one-line reason. Your brief lists them under "Garron's
casebook", this drawing's rulings first. Read that section before you choose a label.
- **Same drawing, same missed size, same wrong number:** use his label.
- **Anything else:** this playbook decides. His reasons are examples of how he applies
  it.

When Garron has already labelled every missed size in a group this way, code copies his
label on and marks the group "reused", so no agent is sent to it.

## Reading the drawing

### Set the part's X/Y/Z frame first

The ground truth gives each missed dimension's axis. It records the physical axis of
the part, not the direction on the page.
- **CUBE:** Thk is Z, W is X, L is Y, unless the brief's table says otherwise.
- **CYL:** L is along the part's axis (usually X). Dia has no axis.

Before judging any number, decide which view shows which pair of axes:
- **Flat, plate-like parts:** the largest view is usually the plan view, showing the
  part's X and Y. Thickness (Z) appears only in the edge or side views.
- **Round parts:** the side view shows the length and diameters. The end view shows the
  round outline.

Keep this frame fixed as you move between views: a vertical dimension in a side view is
not the same axis as a vertical dimension in the plan view.

### Third-angle projection

Nearly all these drawings are third-angle (the brief says which). In third angle, each
view is drawn on the side it is seen from:
- The top view sits **above** the front view.
- The right-side view sits **to the right** of the front view.
- Views line up with each other, so a feature's edge carries straight across from one
  view to the next.

Use that alignment to confirm which view a dimension belongs to. Section views (SECTION
A-A) are cuts, placed wherever there was room. Their orientation comes from the cutting
line on the parent view, not from where they sit on the sheet.

### Trace a dimension line to its own number

A dimension's number belongs to the dimension line it sits on or breaks. It does not
belong to the nearest line. Follow the arrowheads to the extension lines, and the
extension lines to the part edges they measure.
- Leaders with a note (`Ø6.35 THRU`, `12.7 [.50] DP.`) describe a feature, not a
  distance.
- Ordinate dimensions: several numbers measured from a `0` along one direction, with no
  arrowheads. Each gives a position from that zero. The envelope along that direction
  is the largest position, or the sum of the largest positions on each side when zero
  sits inside the part.
- A number far from its line, with a different callout crowded close to that line, is
  the setting of Proximity association.

### Dual `mm [in]` callouts

Most sheets print `mm [in]`, e.g. `69.9 [2.75]`. The bracketed inch number is the same
dimension, not a separate one. Each display is rounded on its own. When a reply gives a
number that matches a bracketed inch value times 25.4, it read that same callout. Treat
an inch-only print (the brief says "inch only") as inch values.

### Chains and datums

- A **chain** is an envelope the sheet never prints as one number. The model has to add
  printed parts (6.50 + 1.00 = 7.50), or subtract an overlap.
- A **datum** is the `0` that ordinate dimensions are measured from. Usually it sits on
  an outside edge.
- **An internal zero:** when the zero is a feature inside the part rather than an edge,
  the envelope is one value from each side of zero added together. A model that reports
  a value from one side only, as if zero were an edge, is what Datum reconstruction
  names. The brief's `Measured From: In-Between Edges` marks these drawings.

## Worked examples (Garron's labels on drawings in this repo)

**Axis mapping: 201548-013 (locator block).** Ground truth 25.400 (Z) × 228.600 (X) ×
241.300 (Y). Gemini gave 85.7 for the thickness. 85.7 runs up and down in the side view,
which is Y there; the thickness (Z) runs up and down only in the bottom view.

**Feature substitution: 201533-020 (bottom plate).** Ground truth 12.700 (Z) × 215.9 (X)
× 184.2 (Y). GPT gave 6.35 [.250] for the thickness. 6.35 is printed in the top edge
view as the position of the tapped holes' centreline: a feature's number in the
thickness direction, not the envelope.

**Chain aggregation: 201551-017 (angle).** Ground truth Thk 100.5 (Z). The side view
gives the depth as two consecutive dimensions, 12.7 [.50] across the upright leg and
87.8 [3.45] along the base leg; GPT gave 87.8 and did not add the 12.7. The overall 100.5
is printed in the top view, and it is still Chain aggregation: the model took a piece
instead of the whole.

**Datum reconstruction: 200951.** Ground truth Thk 34.29 + 6.35 = 40.64 (Z). The
thickness is ordinate-dimensioned from a 0 on datum hole B, inside the part: 34.29 to one
edge and 6.35 to the other. GPT and Gemini gave 34.29, the larger piece on one side of
zero, and missed the 6.35 on the other side.

**Over-aggregation: 201258-012 (flanged round part).** Ground truth Dia 90.4, L 57.150.
Opus gave 65.1, 65.05 and 65.0 in its three runs: it added the 7.9 flange to 57.150,
which is already the full length.

Proximity association has no example among these drawings yet.

## Tools

Run from the project root. Each prints where its picture was saved; open it with Read.

- `uv run vlm-eval drawing-view <drawing>` saves the whole sheet with a light grid
  every 0.1 of its width and height. Start here, and use the grid to name regions.
- `uv run vlm-eval drawing-view <drawing> x0 y0 x1 y1` saves a sharp zoom of that region
  (fractions of the sheet, 0 = left/top, 1 = right/bottom). A smaller region gives more
  detail. Add `--dpi N` only if the default is not sharp enough.
- `uv run vlm-eval drawing-numbers <drawing>` (text drawings) lists every printed number
  with its position as fractions across and down the sheet. Use it to find every place a
  number appears; the same number often appears in several views. On a picture-only
  drawing it says so, and you read the numbers from the zooms instead.
- Arithmetic: `python3 -c "print(34.29 + 6.35)"`. Don't add chains in your head.

A good sequence: the sheet view to learn the layout, then the printed-numbers list for
where the right and wrong numbers sit, then zooms on the missed dimension's own line and
on the wrong number. Usually 3 to 6 zooms are enough.

## Output: `diagnosis.json`

Write it where the brief says, in exactly this shape:

```json
{
  "group": "201513-L-78",
  "diagnoses": [
    {
      "missed": "L (Y)",
      "wrong_value": "78.0",
      "label": "Axis mapping",
      "wrong_value_axis": "X",
      "note": "Two to four plain sentences an engineer can check: what the wrong number measures, where it is, and why the model picked it.",
      "evidence": [
        {
          "number": "78.00",
          "where": "top view, upper left, horizontal overall dimension",
          "view": "runs/diagnoses/views/201513-0.05-0.1-0.45-0.4-400dpi.png"
        }
      ]
    }
  ]
}
```

- **`missed`:** copy it exactly from the brief ("L (Y)", "Thk (Z)", "Dia"). There is one
  entry per missed dimension.
- **`wrong_value`:** the number from the reply that was meant for this dimension. With
  two missed dimensions and two wrong numbers, decide from the drawing which went with
  which; the scorer can't. Use `"none"` only if the reply gave no number for it.
- **`label`:** one of the seven label names listed under the table, spelled exactly.
- **`wrong_value_axis`:** the part axis the wrong number actually measures along.
  - `X`, `Y` or `Z`.
  - `none`: it is not a length along an axis, such as a hole size, a diameter, or a
    number that is printed nowhere.
  - `unclear`.
- **`note`:** plain words, no hedging filler, and evidence rather than guesses.
- **`evidence`:** each number the note relies on, as printed, where it sits (view and
  position), and the zoom that shows it. Include the wrong number if it is printed, and
  the correct dimension's own number.

Then run `uv run vlm-eval check-diagnoses <folder> <group>`. It must say "All checks
passed". If it lists problems, fix them and run it again.

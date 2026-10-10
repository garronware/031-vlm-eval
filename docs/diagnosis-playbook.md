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
| Proximity association (research example 1A) | Found the right dimension line but took a nearby, unrelated number instead of the one that belongs to the line. |
| Axis mapping (research example 1B) | Chose a dimension from the wrong axis. |
| Chain aggregation (research example 2A) | Failed to chain dimensions, chained the wrong dimensions, or failed to subtract a dimension that overlapped. |
| Datum reconstruction (research example 2B) | A chain aggregation failure that happened *because* the dimensions start from an internal datum instead of an outer part edge. The model missed the datum-to-edge segment on the other side of the datum. |
| Over-aggregation | Added a printed size to one that already includes it, so the size comes out too big (e.g. a flange thickness added to a length that already includes the flange). |
| Feature substitution | Correctly read a real dimension in the right axis, but that dimension belongs to a feature, not the outer envelope (e.g. main-body Ø instead of a larger flange Ø, pocket depth, hole spacing). |
| Unclassified | None fit, or the evidence is unclear. Goes to Garron. |

**Tie-breaks**
- Datum reconstruction beats Chain aggregation.
- Chain aggregation is a chain the size needed, missed or built wrong. Over-aggregation
  is a chain built where none was needed: one printed size already gave the answer.
- If two other labels fit equally well, use Unclassified.
- Give exactly one label per missed dimension.

In `diagnosis.json`, write the label's name alone, without the "(research example …)"
part: `Proximity association`, `Axis mapping`, `Chain aggregation`,
`Datum reconstruction`, `Over-aggregation`, `Feature substitution`, `Unclassified`.

Use only these labels. If several failures seem to need a label that doesn't exist,
say so in the note; Garron decides any change to the list.

### Telling the labels apart

These questions stay inside the definitions above. Work through them in order.

1. **Is the missed dimension a chain in the ground truth (`a + b = c`)?** If the model
   gave one of the parts, the wrong parts, or failed to subtract an overlap, it is a
   chain failure. Then look at `Measured From` in the brief:
   - **`In-Between Edges`:** the chain's zero sits between the part's edges, so the
     envelope is a value on one side of zero plus a value on the other. A model that
     missed the other side missed the datum-to-edge segment: **Datum reconstruction**.
   - **`Part Edge`:** **Chain aggregation**.
   - A size the ground truth records as one number can still be **Datum
     reconstruction** when that number is only printed as a reference and the
     dimensions start from an internal zero. On 200951 the length 72.91 [2.870] is in
     parentheses; the models gave 66.6, one side of the zero, and missed the 6.4 on the
     other (Garron, 2026-09-29). These sheets were drawn in inches, so the inch parts add
     up exactly (0.250 + 2.620 = 2.870) where the mm parts may not.
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
   - **The same axis, in a view that could show the size but doesn't dimension it, and
     the number belongs to a feature: Feature substitution.** The test is "could the
     missed size be shown in this view?" If yes, the model substituted a feature's
     number (a hole position, a chamfer corner, a bore, a pocket, a body diameter
     smaller than the flange). 201533-020: the top edge view could show the thickness,
     and the model gave the 6.35 hole-centreline position. 201513: the right-side view
     could show the 64.8 height, and the model gave the 57.8 chamfer-corner position.
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
- **Anything else:** his reasons are precedent, and they outrank this playbook's general
  wording. If your case goes against one of them, say so in the note.

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

Keep this frame fixed as you move between views. The main failure the research found
is models losing track of it: a vertical dimension in a side view is not the same axis
as a vertical dimension in the plan view.

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
- **Garron's point on 2B:** when the zero is an internal feature of the part rather
  than an edge, the model has to add one value from each side of zero. Models most often
  fail here because they assume zero is an edge, as it usually is on 2D drawings. So they
  report the biggest number on one side and never look across the datum. That is what
  Datum reconstruction names. The brief's `Measured From: In-Between Edges` marks these
  drawings.

## Worked examples (Garron's research page, machinable.ai/research.html)

**1A: corrected by Garron. 201533-020 is Feature substitution (2026-09-29).** The
research page gave 201533-020 (bottom plate) as its Proximity association example:
GPT-5.5 gave 6.35 mm for the 12.7 mm Z-axis thickness. Garron has since found he misread
the sheet: 6.35 [.250] is printed on its own in the top edge view, as the position of
the tapped holes' centreline, not between the thickness arrows. On 2026-09-29 he
labelled it Feature substitution: "Not the
wrong view. Thickness could be displayed in this view and it would appear roughly where
6.35 appears ... the model is substituting a hole position for a thickness value." The
Proximity association definition stands; this drawing is no longer its example.

**1B: Axis mapping, 201548-013 (locator block).** Opus 4.6 gave 85.7 mm for
the 25.4 mm Z-axis thickness. The model took the side-section view's vertical Y-axis
dimension for the part's Z thickness, "because it does not consistently maintain a
global part-coordinate frame across orthographic views."

**2A: Chain aggregation, sample drawing 1.** Fable 5 gave 4.987 in for a 5.567 in X-axis
length. It found the largest single dimension but did not add the consecutive axial
dimensions 4.987 and 0.580.

**2B: Datum reconstruction, drawing 2001-19.** Gemini 3.1 Pro gave .754 in for a .949 in
Y-axis envelope. The dimensions are measured from an internal datum, not an outer edge.
The model took the .754 datum-to-edge segment on one side and missed the .195 segment on
the other side of zero. The numbers are only the example. The root cause is the zero
sitting between the part's edges.

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

---
description: Group the failures in a run and explain each group with Garron's failure labels
---

Diagnose why models failed (SPEC 2.6, Chunk 8). Garron is not a developer: use plain
English. Code has already scored every reply. This command only explains the failures.
It sends nothing to any paid model API: the agents run on Garron's Claude plan.

The run to diagnose is `$ARGUMENTS` if given, otherwise `main-stock-shape` (the prompt
in use since 2026-09-20).

## 1. Group the failures (free)

Run `uv run vlm-eval failure-groups <folder>`. It prints each failure group, its brief,
and its state: "to diagnose", "diagnosed", "reused from Garron's label", or "confirmed
by Garron". Identical failures (same drawing, same missed size, same wrong number) are
one group, whichever model made them.

When Garron has already labelled every missed size in a group on the same drawing with
the same wrong number, this step copies his label on automatically, marked "reused",
with the original evidence. Those groups get no agent. If nothing is left to diagnose,
go to step 3.

## 2. Diagnose every waiting group at once

In one message, launch one `failure-diagnostician` agent per group marked "to diagnose",
and for no other group.
Give each its brief path and nothing else: "Your brief is
`runs/diagnoses/<folder>/<group>/brief.md`." If that agent type isn't available in this
session, use a general-purpose agent, telling it: "Read
`.claude/agents/failure-diagnostician.md` and follow it as your instructions." Don't poll;
wait for each to finish.

## 3. Check every diagnosis

Run `uv run vlm-eval check-diagnoses <folder>`. It checks three things for each group:
- one label from Garron's list per missed size
- every cited number is printed on the drawing
- a picture-only drawing's citations are marked "can't check"

It then writes and opens `runs/diagnoses.html`.

For any group it reports, send the problems back to that group's agent once (SendMessage)
and check again. If a problem is still there, leave it: the page shows it to Garron.
Never edit a `diagnosis.json` yourself, and never change a label.

## 4. Tell Garron

In plain words:
- how many groups and failed replies there were
- how many groups were reused from his earlier labels, counted separately from the
  groups the agent diagnosed
- how many got each label, counted from the diagnosis files, not from memory
- any group still showing a problem
- that the list is open in his browser at `runs/diagnoses.html`

For the first run on a set, remind him to read 201533-020 if it failed (Feature
substitution, his correction of research example 1A), 201548-013 if it failed (Axis
mapping, research example 1B), plus
about 5 others, and to say whether the notes make sense.

# Backlog

Gaps found while working, not yet in a spec.

- Advice agents state derived numbers (error at a mesh size, model-size ratios) without checking
  them; the cylinder held-out advice failed twice on one (002 Log). Candidate skill rule: every
  number in the advice comes from the workflow step-5 hand calc or carries [TBD].
- Advice tags sometimes point at a neighbouring rule (C10 vs C7, G2 vs G1); the skill's tag layout
  may need one tag per rule.
- M13 element sizing at a stress peak has no source; stays [TBD].
- Kt handbook source (Peterson, Pilkey or Roark) for the plate-with-hole check.
- C2 idle detection: the AFXProcedure counter is unproven; a stuck counter blocks every live script.
- Held-out models should avoid physics with a ready Abaqus benchmark page (Hertz has one).

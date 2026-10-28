# Rigid tools and contact

Source tags as in `SKILL.md`. Abaqus 2026 terms: `main` and `secondary`.

## Rigid bodies and analytical rigid surfaces

- R1. Rigid bodies suit tooling such as punches, dies and blank holders, and save computation.
  `[A: Rigid Body Definition]`
- R2. A rigid body moves through BCs or loads at its reference node.
  `[A: Rigid Body Definition]`
- R3. The reference node DOFs of an analytical rigid surface become active only once the surface is in a contact interaction or an element connects to the node.
  `[A: Analytical Rigid Surface Definition]`
- R4. An analytical rigid surface is single-sided and always the main surface. Its contact pressure cannot be contoured: read CPRESS on the secondary surface.
  `[A: Analytical Rigid Surface Definition]`
- R5. Its outward normal must point toward the contacted body. Segment order sets the normal (gotcha in `SKILL.md`).
  `[A: Analytical Rigid Surface Definition]` `[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
- R6. Sharp corners between rigid segments hurt finite-sliding convergence. Smooth them with a fillet radius (default 0, no smoothing).
  A fillet radius larger than an adjoining segment has no effect.
  `[A: Analytical Rigid Surface Definition]` `[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
- R7. Extend the rigid surface, or add corners at its perimeter, so secondary nodes cannot slide off its end. A node behind the surface usually ends convergence.
  `[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
- R8. In an axisymmetric model the rigid profile lies in the r–z plane (e1 = r, e2 = z).
  `[A: Analytical Rigid Surface Definition]`

## Contact formulation

- C1. Surface-to-surface discretization gives more accurate contact stress and pressure than node-to-surface.
  The docs' benchmark table shows CPRESS errors of 13–31 % for node-to-surface against about 1 % for surface-to-surface.
  Use surface-to-surface when contact pressure or local stress is a result.
  `[A: Contact Formulations in Abaqus/Standard]`
- C2. Surface-to-surface is less sensitive to the main/secondary choice. It becomes expensive when the secondary mesh is much coarser than the main.
  `[A: Contact Formulations in Abaqus/Standard]`
- C3. A node-based surface forces node-to-surface discretization.
  `[A: Contact Formulations in Abaqus/Standard]`
- C4. A contact pair with no discretization option in the input file is finite-sliding node-to-surface. `model_summary` does not report the discretization: check it in the interaction editor.
  `[A: Contact Formulations in Abaqus/Standard]`
- C5. Contact is a constraint, enforced by Lagrange multipliers (direct) or a penalty.
  `[Bathe 6.7]` `[Bathe 3.4.1]` `[Reddy 6.4]`

## Main and secondary

- C6. Analytical rigid and rigid-element surfaces must be main.
  `[A: Contact Formulations in Abaqus/Standard]`
- C7. Otherwise choose as main: the larger surface; with similar sizes, the stiffer body; then the coarser mesh.
  Judge stiffness of the structure, not only of the material: a thin sheet can be softer than a rubber block.
  `[A: About Contact Pairs in Abaqus/Standard]` `[A: Contact Formulations in Abaqus/Standard]`
- C8. The secondary surface must lie on the side of the main surface's outward normal. A wrong normal often causes immediate non-convergence.
  `[A: About Contact Pairs in Abaqus/Standard]`
- C9. With node-to-surface, main nodes can penetrate the secondary surface. Refine the secondary surface or use a symmetric pair.
  `[A: About Contact Pairs in Abaqus/Standard]`

## Normal behaviour and enforcement

- C10. Hard contact is the default pressure-overclosure relation.
  `[A: Contact Pressure-Overclosure Relationships]`
- C11. Default enforcement: penalty for finite-sliding surface-to-surface hard contact; direct otherwise.
  The penalty method is efficient at a small accuracy cost. With direct hard contact, avoid overconstraints.
  `[A: Contact Formulations in Abaqus/Standard]` `[A: Contact Constraint Enforcement Methods in Abaqus/Standard]`

## Friction

- C12. Contact is frictionless by default. Ask the user for μ and its origin.
  `[A: Frictional Behavior]`
- C13. The default penalty friction allows elastic slip up to γcrit = Ff·l̄, with Ff = 0.005 by default and l̄ the characteristic contact surface length.
  A very small slip tolerance gives convergence trouble. The Lagrange multiplier method is the alternative.
  `[A: Frictional Behavior]`
- C14. With μ > 0.2 Abaqus switches the unsymmetric solver on automatically.
  `[A: Frictional Behavior]`
- C15. Friction cannot hold a body before contact pressure develops. Start in contact, or move into contact with a BC in step 1 and remove it later.
  `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]`

## Initial overclosure

- C16. Contact-pair overclosures at the start are treated as interference fits by default and resolved in the first increment.
  `[A: Contact Initialization for Contact Pairs in Abaqus/Standard]` `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]`
- C17. An adjustment zone moves secondary nodes onto the main surface strain-free. Use it for small meshing gaps and overclosures that are not intended.
  `[A: Contact Initialization for Contact Pairs in Abaqus/Standard]`
- C18. Check with COPEN at increment 0 of the first step: negative values are overclosures.
  `[A: About Contact Pairs in Abaqus/Standard]`

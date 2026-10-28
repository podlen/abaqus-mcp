# Elements and mesh

Source tags as in `SKILL.md`.

## Element choice

- E1. Use quadrilaterals and hexahedra where the geometry allows. Avoid first-order triangles and tetrahedra (CPE3, CPS3, CAX3, C3D4) in stress analysis.
  `[A: Solid (Continuum) Elements]`
- E2. First-order elements are recommended when large strains or very high strain gradients are expected. This covers most forming and contact-with-plasticity models.
  `[A: Solid (Continuum) Elements]`
- E3. First-order reduced integration (CPS4R, CPE4R, CAX4R, C3D8R):
  - suited to large distortion, and the first choice when distortion is severe;
  - no volumetric locking: first-order quads and hexes have constant volumetric strain;
  - shear locking concerns only the fully integrated first-order elements (E4);
  - has hourglass modes, needs hourglass control and a reasonably fine mesh;
  - in bending with large distortion, use a fine mesh of these elements.
  `[A: Solid (Continuum) Elements]` `[Bathe 5.5.6]`
- E4. First-order full integration (CPE4, CAX4, C3D8) uses selectively reduced integration. It does not lock volumetrically under plasticity.
  It shear-locks in bending, worst when the element length is at least the wall thickness.
  `[A: Solid (Continuum) Elements]` `[Reddy 12.5]` `[Reddy 5.3.4]`
- E5. Incompatible-mode elements (CPS4I, CPE4I, CAX4I, C3D8I):
  - full integration, no hourglassing, no parasitic shear: the choice for bending-dominated regions;
  - accuracy drops for parallelogram shapes and further for trapezoids, so they need near-rectangular meshes;
  - use with caution under large compressive strains: slow convergence and inaccuracy are possible.
  `[A: Solid (Continuum) Elements]` `[Bathe 4.4.1]`
- E6. Second-order reduced integration (CPE8R, CAX8R, C3D20R) suits smooth problems.
  Second-order full integration suits stress concentrations, except at finite strain of nearly incompressible material.
  `[A: Solid (Continuum) Elements]`
- E7. Second-order fully integrated elements (CPE8, CAX8, C3D20) lock volumetrically once plastic strains reach the order of the elastic strains (Mises plasticity is isochoric).
  Symptom: a checkerboard pattern of integration-point pressure (quilt plot).
  `[A: Solid (Continuum) Elements]` `[Bathe 4.4.3]` `[Bathe 4.5]`
- E8. C3D10M is the tetrahedron for large plastic deformation and contact: minimal shear and volumetric locking, robust at finite deformation.
  Do not connect it to regular second-order elements.
  `[A: Solid (Continuum) Elements]`
- E9. Regular second-order tetrahedra (C3D10) cannot underlie a secondary surface in node-to-surface contact with strict hard contact.
  `[A: Solid (Continuum) Elements]`
- E10. Hybrid elements (suffix H) give no advantage for elastic-plastic materials. Do not use them there.
  `[A: Solid (Continuum) Elements]`
- E11. Shells: general-purpose conventional shells (S4R, S3R, SAX1) are robust for most applications. Continuum shells (SC6R, SC8R) work for any thickness and allow two-sided contact with thickness change.
  `[A: Choosing a Shell Element]`
- E12. In elastic-plastic bending, too few integration points across the bent section misrepresent the spread of yielding and the limit load.
  `[Bathe 6.8.4]`

## Hourglass control

- H1. Abaqus/Standard defaults to total-stiffness hourglass control for first-order reduced-integration elements.
  `[A: Section Controls]`
- H2. Enhanced hourglass control is more accurate on coarse meshes. It can give an overly stiff response in plastic bending.
  `[A: Section Controls]`
- H3. Judge hourglassing by ALLAE against ALLIE (see `solution-and-checks.md`, rule G2).
  `[A: Whole and Partial Model Variables]`

## Mesh refinement

- M1. Refine where the solution changes fast: contact zones, notches, load points, geometric and material discontinuities. Keep the mesh coarse where gradients are low.
  `[Reddy 9.3.2]` `[Reddy 10.4.3]` `[A: Mesh convergence]`
- M2. A well-graded mesh has about the same error density in each element.
  `[Bathe 4.3.5]`
- M3. A non-smooth solution lowers the convergence order of uniform refinement.
  `[Bathe 4.3.5]`
- M4. A sharp re-entrant corner is a stress singularity: its peak stress grows with every refinement and never converges.
  If stress there matters, model the real fillet radius. Away from the corner the global response is barely affected.
  `[A: Mesh convergence]`
- M5. Stresses converge more slowly than displacements. Converge the mesh on the quantity of interest.
  `[A: Mesh convergence]`
- M6. Avoid poor aspect ratios and included angles, most of all in high-gradient regions. The element Jacobian must stay positive.
  `[Reddy 10.4.2]` `[Reddy 10.4.3]`
- M7. Distortion raises the error. Under small distortion the convergence order is unchanged.
  Under NLGEOM, elements distort further as they deform.
  `[Bathe 6.8.3]` `[A: General and Perturbation Procedures]`
- M8. Contact spread over a single element face gives unreliable results. Refine until several elements share the contact.
  `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]`
- M9. The deformable mesh must be finer than the smallest feature of a rigid surface it touches. Otherwise the feature penetrates it.
  `[A: Modeling issues for rigid surfaces in Abaqus/Standard]`
- M10. With node-to-surface contact, main nodes can penetrate a coarse secondary surface. Refine the secondary surface.
  `[A: About Contact Pairs in Abaqus/Standard]`
- M11. Stress jumps between elements in unaveraged output measure discretization error. Inspect unaveraged contours before trusting a peak.
  `[Bathe 4.3.6]`
- M12. Run a mesh convergence study: refine (h) and compare the quantity of interest until the change is negligible for the user's accuracy target.
  `[A: Mesh convergence]` `[Reddy 3.6.3]`
- M13. First-order reduced-integration elements (CPS4R, CAX4R, C3D8R) have one integration point `[A: Solid (Continuum) Elements]`. For linear elements the stress is evaluated at the centre of the element `[Reddy 12.4.7]`. A surface peak is therefore read about half an element inside the surface.
  Size the first element at the peak surface from the hand-calc stress gradient so that the stress at that depth is within the user's accuracy target `[TBD]`.
  For smooth elastic problems with stress concentrations, second-order elements capture them more effectively `[A: Solid (Continuum) Elements]`; E2 prefers first-order elements for large strains and contact.
  Confirm with a mesh refinement (M12).

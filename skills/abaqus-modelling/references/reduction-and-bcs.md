# Reduction, boundary conditions and loads

Source tags as in `SKILL.md`.

## Symmetry

- S1. Reduce to a symmetric portion only when geometry, material, loads and boundary conditions are all symmetric about the same plane.
  `[Reddy 9.3.1]`
- S2. The symmetry plane becomes part of the model boundary and carries symmetry conditions.
  `[Reddy 9.3.1]`
- S3. XSYMM fixes DOF 1, 5, 6 on a plane X = const; YSYMM fixes 2, 4, 6; ZSYMM fixes 3, 4, 5.
  `[A: Boundary Conditions]`
- S4. Avoid antisymmetry conditions in problems with finite rotations.
  `[A: Boundary Conditions]`
- S5. A symmetry condition also forces a symmetric response. It suppresses a non-symmetric buckling or collapse mode.
  Ask the user whether such a mode is possible before reducing.
  `[TBD]`

## Axisymmetry

- X1. An axisymmetric (r–z) model is valid only when geometry, material, loads and BCs do not vary with θ.
  Otherwise the solution is three-dimensional.
  `[Reddy 9.3.1]`
- X2. In axisymmetric models r and z are the global X and Y directions.
  `[A: Choosing the Element's Dimensionality]`
- X3. The radial coordinate of every node must stay positive. A prescribed radial motion must not violate this.
  `[A: Boundary Conditions]`
- X4. Abaqus applies no boundary condition on the symmetry axis. Prescribe u_r = 0 on nodes at r = 0 for nonlinear problems.
  Exception noted in the docs: penetration calculations.
  `[A: Axisymmetric Solid Element Library]` `[A: Choosing the Element's Dimensionality]`
- X5. A point load in an axisymmetric model is the total load on the ring, integrated over 2π.
  `[A: Axisymmetric Solid Element Library]`
- X6. An axisymmetric rigid body has three active DOFs at its reference node. Only axial displacement is a rigid-body mode.
  Drive U2 and fix U1 and UR3 at the reference point.
  `[A: Rigid Body Definition]`

## Plane models

- P1. Plane stress (CPS) suits thin bodies loaded in their plane. Plane strain (CPE) suits bodies where the out-of-plane strain is zero.
  `[A: Choosing the Element's Dimensionality]`

## Boundary conditions and loads

- B1. Prescribe either the displacement or the force at a DOF, never both. When both seem known, prescribe the displacement.
  `[Reddy 9.3.3]`
- B2. On first-order reduced-integration meshes (CPS4R, CPE4R, CAX4R, C3D8R) spread point loads and point BCs over several nodes. A single loaded node excites hourglass modes.
  `[A: Solid (Continuum) Elements]`
- B3. Drive a rigid tool through a BC at its reference node. The reference node position matters for nonzero rotations and moments.
  `[A: Rigid Body Definition]`
- B4. Place a node at each point load, and refine near load and geometric discontinuities.
  `[Reddy 9.3.2]`
- B5. Load control cannot pass a limit point: the tangent stiffness is singular there.
  For proportional loading use the modified Riks method.
  `[A: Static Stress Analysis]` `[Bathe 8.4.3]`
- B6. A prescribed tool displacement passes a force maximum in a Static General step.
  `[TBD]`
- B7. Constrain every active DOF of a free body in step 1. Friction cannot hold a body before contact pressure develops.
  Use a temporary BC that moves the body into contact, removed in a later step, or soft springs or dashpots.
  `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]`

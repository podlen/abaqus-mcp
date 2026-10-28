# Solution, convergence and checks

Source tags as in `SKILL.md`.

## NLGEOM

- N1. Switch NLGEOM on when large displacements, rotations or strains are expected. Abaqus/Standard defaults to small displacement.
  `[A: Static Stress Analysis]` `[A: General and Perturbation Procedures]` `[Bathe 6.2.3]` `[Bathe 6.6.4]`
- N2. Once NLGEOM is on in a step, it stays on in all following steps.
  `[A: General and Perturbation Procedures]`
- N3. Contact constraints track large sliding even with NLGEOM off. Contact sliding alone is no proof that NLGEOM is on.
  `[A: General and Perturbation Procedures]`
- N4. Run a linear model first. It shows where yielding and large displacements appear. Then add nonlinearities one at a time.
  `[Bathe 6.8.1]`

## Static General incrementation

- I1. Use automatic incrementation. Increments must be small enough to follow history-dependent plasticity; Newton iteration has a finite radius of convergence.
  `[A: Static Stress Analysis]` `[Bathe 8.4.1]`
- I2. Give an initial increment. Without one, Abaqus tries the whole step load in one increment.
  `[A: Solving Nonlinear Problems]`
- I3. Default behaviour: after 16 iterations, or on divergence, the increment restarts at 25 % of its size.
  The run stops below `min_inc` or after more than 5 attempts.
  The increment grows by 50 % after 2 consecutive increments that converge in fewer than 5 iterations.
  `[A: Solving Nonlinear Problems]`
- I4. An increment is abandoned when the residual fails to decrease over two consecutive iterations.
  `[A: Convergence Criteria for Nonlinear Problems]`
- I5. Default solution controls need no change in most cases. Change one only with a diagnosed cause.
  `[A: About Convergence and Time Integration Criteria]`
- I6. For strongly nonlinear problems that diverge, activate line search (Nls ≈ 5). It is on by default only with quasi-Newton.
  `[A: Commonly Used Control Parameters]`
- I7. Do not force fixed increments through non-convergence (DIRECT, NO STOP).
  `[A: Static Stress Analysis]`

## Convergence diagnosis

Read `job_status(job)` first: it groups `.msg` warnings per step.

| symptom | likely cause | action | source |
|---|---|---|---|
| "Numerical singularity" warnings, very large displacements | unconstrained rigid-body motion: free reference point, body held only by friction | constrain every active DOF; start in contact or use temporary BCs or soft springs | `[A: Common Difficulties Associated with Contact Modeling in Abaqus/Standard]` |
| severe overclosure at every secondary node from increment 1 | rigid surface normal points away from the body | reverse the segment order | `[A: Modeling issues for rigid surfaces in Abaqus/Standard]` |
| zero contact force while the tool moves through the body | same-direction normals with surface-to-surface: contact ignored | reverse the segment order | `[A: About Contact Pairs in Abaqus/Standard]` |
| negative eigenvalue or zero pivot warnings | tangent stiffness not positive definite: limit load, buckling, softening, or ill conditioning from poor element shapes | locate the region in Job Diagnostics; past a physical limit point use Riks (proportional load) or stabilization (local instability) | `[A: Iterative Linear Equation Solver]` `[A: Job diagnostics]` `[Bathe 8.2.5]` `[Bathe 8.4.3]` `[A: Static Stress Analysis]` |
| excessive distortion, or very large plastic strain increment | element or material calculation failed | Abaqus retries at 0.25 of the increment; with fixed stepping it terminates. Reduce `max_inc`, regrade the mesh there, fillet rigid corners, use first-order reduced elements | `[A: Convergence Criteria for Nonlinear Problems]` `[A: Solid (Continuum) Elements]` `[A: Analytical Rigid Surface Definition]` |
| repeated cut-backs at one stroke, secondary nodes near a rigid edge | nodes sliding off the rigid surface | extend the rigid surface | `[A: Modeling issues for rigid surfaces in Abaqus/Standard]` |
| cut-backs until `min_inc` | increment too large for the nonlinearity, or `min_inc` too high | smaller initial increment, lower `min_inc` | `[A: Solving Nonlinear Problems]` |

## Automatic stabilization

- T1. Use automatic stabilization for local instabilities (wrinkling, material instability, local buckling). Riks does not suit them.
  `[A: Static Stress Analysis]`
- T2. The default dissipated energy fraction is 2.0 × 10⁻⁴. The adaptive scheme limits ALLSD/ALLIE to an accuracy tolerance.
  `[A: Solving Nonlinear Problems]`
- T3. After a stabilized run, compare ALLSD with ALLIE, and viscous forces VF with the expected nodal forces. Viscous forces must not dominate.
  `[A: Solving Nonlinear Problems]`

## Energy checks

Pull the series with `odb_history(job, outputs=["ALLIE", "ALLAE", "ALLSD", "ALLPD"])`.

- G1. ALLAE is the artificial strain energy of hourglass and drill constraints. ALLIE = ALLSE + ALLPD + ALLCD + ALLAE + ALLQB + ALLEE + ALLDMD.
  `[A: Whole and Partial Model Variables]`
- G2. Compare ALLAE with ALLIE over the whole step. Two Abaqus/Explicit tutorials call about 2 % "not a problem" and about 15 % "substantial".
  No Standard-specific threshold was found. Agree a limit with the user.
  `[A: Getting Started with Abaqus/CAE > Materials > Example: blast loading on a stiffened plate > Postprocessing]`
  `[A: Getting Started with Abaqus/CAE > Contact > Abaqus/Explicit example: circuit board drop test > Postprocessing]`
- G3. A high ALLAE/ALLIE calls for a finer mesh, loads and BCs spread over several nodes, or another element family (E4, E5).
  Enhanced hourglass control is the other option; it can stiffen plastic bending.
  `[A: Solid (Continuum) Elements]` `[A: Section Controls]`

## Verification and validation

- V1. Check the linear part first: compare the initial slope of the force-displacement curve, or the elastic response of a linear run, with a hand calc.
  `[Bathe 6.8.1]`
- V2. Compare a plastic quantity (first-yield force, limit load) with a hand estimate from the yield stress and the loaded section.
  `[TBD]`
- V3. Repeat with a finer mesh and a smaller `max_inc`. The quantity of interest must not change beyond the user's target.
  `[A: Mesh convergence]` `[A: Static Stress Analysis]`
- V4. Check for locking (checkerboard pressure) and for stress jumps in unaveraged contours before trusting a peak stress.
  `[A: Solid (Continuum) Elements]` `[Bathe 4.3.6]`
- V5. Compare PEEQ in the result with the last plastic strain in the material table. Beyond it, the yield stress is held constant by default.
  `[A: Classical Metal Plasticity]`

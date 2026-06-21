# Model Selection Roadmap

This project should treat single-curve dark JV fitting as a nested model-selection
problem, not as a search for one universal model. The production path should keep
equivalent-circuit fits stable while marking higher-physics candidates as
metadata-aware diagnostics unless the data and metadata support stronger claims.

## Internal Convention

- Use internal branch voltage `U` for all models, with `V = U + J Rs`.
- Use signed current internally: reverse bias `V < 0` should have `J < 0`.
- Use log-magnitude residuals as the default objective for wide-dynamic-range
  dark current fitting, with explicit sign handling and a linear fallback near
  the noise floor.

## Candidate Matrix

| ID | Model | Mechanism | Default role |
| --- | --- | --- | --- |
| M0 | diode + Rs | baseline diode transport with series resistance | baseline |
| M1 | diode + Rs + Rsh | ohmic shunt / leakage path | reportable equivalent shunt |
| M2 | diode + Rs + Rsh + `k abs(U)^m sign(U)` | empirical non-ohmic leakage | production full model |
| M3 | no-k fallback | M2 with `k` effectively absent | automatic fallback candidate |
| M4 | clean double diode / recombination-diffusion | diffusion plus SRH-like recombination | first-stage physical candidate |
| M5 | SCLC / TFL | trap-limited bulk injection | diagnostic only |
| M6 | Poole-Frenkel-like | field-assisted trap emission | diagnostic only |
| M7 | TAT-like | trap-assisted tunneling | diagnostic only |
| M8 | CQD heterointerface | PbS CQD / ETL interface transport | metadata-aware diagnostic candidate |
| M9 | interface generation / injection barrier | interface states or contact injection | diagnostic unless matched devices support it |

## Nested Selection

1. Start from M0.
2. Add Rsh when near-zero or reverse residuals look like linear leakage.
3. Add `k abs(U)^m sign(U)` only when M1 leaves systematic reverse or high-field
   curvature.
4. Prefer M3 no-k when `k` is near its lower bound, contributes less than 1-3%
   across relevant regions, or M2 improves BIC by less than 2.
5. Try M4 only when forward semilog residuals show two slope regions. Prefer
   fixed idealities near `nd=1`, `nr=2`; free idealities require enough data and
   no boundary hits.
6. Run PF/TAT/SCLC/interface candidates as diagnostics for high-field residuals.
7. Run CQD heterointerface candidates only as metadata-aware diagnostics unless
   the record includes stack and unit metadata sufficient for stronger claims.

## Acceptance Rules

- Primary sort: BIC. Secondary sort: AIC, mean error, max error.
- A complex candidate must improve BIC by at least 6, improve mean error in a
  practically meaningful way, and not worsen max error.
- Region errors must make sense: at least one target region should improve
  without sacrificing the core region.
- Boundary hits downgrade confidence.
- Identifiability checks should include multistart consistency, covariance or
  Hessian conditioning when available, bootstrap/profile likelihood when needed.
- If Rsh and k are strongly coupled, report combined leakage and warn rather
  than forcing a physical split.

## Literature Sources

Use recent CQD photodiode papers as the application context, and use older
semiconductor papers only as the foundational equations behind the diagnostic
families. These sources justify candidate inclusion and parameter sanity checks;
they do not prove that a single dark JV curve uniquely identifies the named
mechanism.

Recent PbS CQD / photodiode context:

- M8-M9 PbS CQD heterointerface and interface-state context comes from the
  repository prior file `docs/LITERATURE_PRIORS_PBS_CQD_NORMAL_PD.md`,
  especially Fang 2025,
  https://doi.org/10.1002/inc2.70003, and Zhong 2026,
  https://doi.org/10.1002/admt.70952.
- Wang, Hu, Yuan, Xia, et al., "Colloidal PbS Quantum Dot Photodiode Imager with
  Suppressed Dark Current," ACS Applied Materials and Interfaces, 2023,
  https://doi.org/10.1021/acsami.3c12918.
- Xu, Meng, Sinha, Chowdhury, et al., "Ultrafast Colloidal Quantum Dot Infrared
  Photodiode," ACS Photonics, 2020,
  https://doi.org/10.1021/acsphotonics.0c00363.
- Xia, Lv, Ran, Yuan, et al., "Ultralow Dark Current and Broadband PbS Colloidal
  Quantum Dot Photodetectors," ACS Photonics, 2026,
  https://doi.org/10.1021/acsphotonics.6c00366.
- Colbert, Placencia, Ratcliff, Boercker, et al., "Enhanced Infrared Photodiodes
  Based on PbS/PbClx Core/Shell Nanocrystals," arXiv, 2021,
  https://doi.org/10.48550/arXiv.2103.12006.
- Pang, Deng, Kheradmand, Hagelsieb, et al., "A silicon photonics
  waveguide-coupled colloidal quantum dot photodiode sensitive beyond 1.6 um,"
  arXiv, 2024, https://doi.org/10.48550/arXiv.2405.12376.

Foundational device-physics references:

- M0-M4 diode, shunt, and recombination/diffusion candidates use the standard
  diode and SRH recombination background from Shockley, "The Theory of p-n
  Junctions in Semiconductors and p-n Junction Transistors," Bell System
  Technical Journal, 1949,
  https://doi.org/10.1002/j.1538-7305.1949.tb03645.x; and Shockley and Read,
  "Statistics of the Recombinations of Holes and Electrons," Physical Review,
  1952, https://doi.org/10.1103/PhysRev.87.835.
- M2 empirical non-ohmic leakage is intentionally treated as a residual-capture
  branch. Do not label it as SCLC, PF, TAT, or interface transport unless the
  relevant diagnostic candidate and metadata also support that interpretation.
- M5 SCLC / trap-filled-limit diagnostics: Lampert, "Simplified Theory of
  Space-Charge-Limited Currents in an Insulator with Traps," Physical Review,
  1956, https://doi.org/10.1103/PhysRev.103.1648.
- M6 Poole-Frenkel-like diagnostics: Frenkel, "On Pre-Breakdown Phenomena in
  Insulators and Electronic Semi-Conductors," Physical Review, 1938,
  https://doi.org/10.1103/PhysRev.54.647.
- M7 TAT-like diagnostics: Hurkx, Klaassen, and Knuvers, "A New Recombination
  Model for Device Simulation Including Tunneling," IEEE Transactions on
  Electron Devices, 1992, https://doi.org/10.1109/16.121690.

## First Implementation Stage

Implement and harden these in order:

1. M0 diode + Rs.
2. M1 diode + Rs + Rsh.
3. M2 diode + Rs + Rsh + k, plus automatic M3 no-k downgrade.
4. Clean M4 recombination/diffusion, without mixing the legacy `k` branch.
5. M8 CQD heterointerface S20/S25 as a metadata-aware diagnostic candidate.

Keep SCLC/TFL, PF-only, TAT, interface-generation, trap-fill, and rollover models
as diagnostic-only candidates until metadata and repeated measurements support
stronger conclusions.

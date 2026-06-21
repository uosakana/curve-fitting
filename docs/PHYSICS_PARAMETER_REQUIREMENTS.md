# Physics Parameter Requirements

This note explains how to obtain the material parameters needed by the advanced
models. For the first app version, these fields should be treated as priors or
metadata, not as parameters freely inferred from one dark JV curve.

## Thickness

Current working value:

```yaml
active_layer_thickness_nm: 350
active_layer_thickness_cm: 3.5e-5
source: user_process_estimate_ink
```

A profilometer, ellipsometry, AFM step height, SEM cross-section, or calibrated
spin-coating recipe can upgrade this from estimate to measured value.

## Relative Permittivity

For SCLC, PF, and capacitance-related estimates, the model needs relative
permittivity `epsilon_r`.

Best direct route:

```text
epsilon_r = C * d / (epsilon_0 * A)
```

where:

```text
C = geometric capacitance in F
 d = film thickness in cm
 A = active or masked area in cm2
epsilon_0 = 8.854e-14 F/cm
```

What you need:

- Capacitance or impedance data on the same device stack or a clean capacitor
  stack.
- Active or masked area.
- Film thickness.
- Frequency, AC amplitude, DC bias, and equivalent-circuit choice.
- A note on whether the value is static/low-frequency or optical/high-frequency.

Optical estimate:

```text
epsilon_optical ~= n^2
```

where `n` is refractive index from ellipsometry. This is useful for
Poole-Frenkel consistency checks, but it is not the same as low-frequency/static
permittivity.

## Mobility

A single dark JV curve from a full photodiode stack usually cannot identify a
true mobility. It can only produce an effective coefficient. For physical SCLC,
use a single-carrier device or independent transport measurement.

Trap-free SCLC estimate:

```text
J = (9/8) * epsilon_0 * epsilon_r * mu * V_eff^2 / d^3
mu = 8 * J * d^3 / (9 * epsilon_0 * epsilon_r * V_eff^2)
```

where:

```text
J = current density in A/cm2
mu = mobility in cm2/V/s
d = active layer thickness in cm
V_eff = voltage across the active layer after contact, built-in, and Rs corrections
```

What you need:

- Current density `J`, not only current `I`.
- Thickness `d`.
- Relative permittivity `epsilon_r`.
- A voltage window where log(J) vs log(V_eff) has slope close to 2.
- Evidence that injection is ohmic and transport is single-carrier.
- Electron-only or hole-only structure if possible.

Alternative mobility sources:

- Electron-only / hole-only SCLC device.
- FET transfer curve mobility.
- TOF, CELIV, Hall, or photoconductivity measurement.
- Literature prior for the same CQD size, ligand, passivation, and film process.

## Trap Density From TFL

If a clear trap-filled-limit voltage exists:

```text
N_t = 2 * epsilon_0 * epsilon_r * V_TFL / (q * d^2)
```

where:

```text
q = 1.602e-19 C
d = active layer thickness in cm
V_TFL = trap-filled-limit transition voltage
```

This requires a real TFL transition, not just a curved diode residual.

## What To Provide Next

For advanced physical models, the highest-value missing inputs are:

- Capacitance or impedance measurement for `epsilon_r`.
- Ellipsometry refractive index if PF optical permittivity is needed.
- Electron-only or hole-only device JV for mobility.
- Temperature-dependent dark JV for PF/TAT discrimination.
- Thickness measurement or thickness series.
- Confirmed stack, contacts, ligand/passivation, and whether the XLSX current is
  `A` or `A/cm2`.

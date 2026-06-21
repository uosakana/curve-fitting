# Device Fit Metadata Template

Use one YAML record for one measured device, one raw JV file, or one literature
prior. Leave unknown values blank, but always keep a `source` field so the model
can distinguish measured values from estimates, literature priors, and working
assumptions.

Internal fit convention:

- Voltage is in `V`.
- Current can be `A` or `A_per_cm2`, but the unit must be explicit.
- Signed current is preferred: reverse bias `V < 0` should have `J < 0`.
- If the source reports reverse current as a positive magnitude, set
  `current_sign_convention: magnitude` and explain it in `current_sign_note`.
- `fit_current_floor` is a current or current-density floor used for fitting
  weights. Do not put spectral noise density directly in this field.

## Record Template

```yaml
record:
  record_id:
  record_type: measured_device_or_literature_prior
  status: draft_or_verified
  owner:
  notes:

source:
  raw_jv_files:
    - path:
      file_type: xlsx_txt_csv_pdf_digitized
      parser: spreadsheet_or_wide_txt_block_or_manual
      sheet_or_block:
      mode: dark_light_both
      voltage_range_V:
      voltage_step_V:
      point_count:
      voltage_column_or_range:
      current_column_or_range:
      current_column_meaning: I_A_or_J_A_per_cm2
      source: measured_literature_assumed
  publication:
    title:
    doi:
    pdf_or_si:
    publication_window:

sample:
  sample_id:
  batch_id:
  device_id:
  measurement_date:
  dark_or_light: dark
  temperature_K:
    value:
    source:
  atmosphere:
    value:
    source:
  instrument:
    value:
    source:
  scan:
    direction:
    rate_or_dwell:
    nplc:
    compliance_A:
    repeat_scan_count:

data:
  current_unit: A_or_A_per_cm2
  voltage_unit: V
  current_sign_convention: signed_magnitude_unknown
  current_sign_note:
  fit_current_floor:
    value:
    unit: A_or_A_per_cm2
    source: measured_estimated_assumed
    note:
  spectral_noise:
    value:
    unit: A_per_sqrtHz
    frequency_Hz:
    bandwidth_Hz:
    source:
    note: Convert through bandwidth before using as a fit current floor.

geometry:
  active_area_cm2:
    value:
    source:
  masked_area_cm2:
    value:
    source:
  active_layer_thickness_nm:
    value:
    source:
  active_layer_thickness_cm:
    value:
    source:
  device_shape:
  contact_geometry:

stack:
  substrate:
    material:
    treatment:
  bottom_electrode:
    material:
    thickness_nm:
    work_function_eV:
  etl:
    material:
    thickness_nm:
    treatment:
  active_layer:
    material:
    thickness_nm:
    ligand:
    passivation:
    absorption_peak_nm:
    bandgap_eV:
    qd_diameter_nm:
    qd_center_distance_nm:
  htl:
    material:
    thickness_nm:
    ligand:
    treatment:
  top_interlayer:
    material:
    thickness_nm:
  top_electrode:
    material:
    thickness_nm:
    work_function_eV:

baseline_M0_M3_priors:
  thermal_voltage:
    temperature_K:
    source:
  ideality_factor_n:
    value:
    lower:
    upper:
    source:
  dark_saturation_current:
    expected:
    lower:
    upper:
    unit: A_or_A_per_cm2
    source:
  series_resistance:
    expected:
    lower:
    upper:
    unit: ohm_or_ohm_cm2
    source:
  shunt_resistance:
    expected:
    lower:
    upper:
    unit: ohm_or_ohm_cm2
    source:
  reverse_leakage_window_V:
  core_fit_window_V:
  forward_fit_window_V:
  nonohmic_exponent_m:
    fixed_value:
    scan_values:
    source:

double_diode_M4_priors:
  evidence_two_forward_slopes: yes_no_unknown
  forward_semilog_windows_V:
  diffusion_ideality_nd:
    fixed: 1.0
    allow_fit: false
    source:
  recombination_ideality_nr:
    fixed: 2.0
    allow_fit: false
    source:
  temperature_series_available: yes_no
  dark_light_comparison_available: yes_no

sclc_tfl_diagnostic_priors:
  active_layer_thickness_cm:
    value:
    source:
  relative_permittivity:
    value:
    source:
  mobility_cm2_per_Vs:
    value:
    carrier_type:
    source:
  ohmic_injection_contact_evidence:
  trap_filled_limit_voltage_V:
  trap_density_cm3:
  thickness_series_available: yes_no

poole_frenkel_diagnostic_priors:
  field_thickness_cm:
    value:
    source:
  relative_permittivity_static:
    value:
    source:
  relative_permittivity_optical:
    value:
    source:
  trap_barrier_eV:
    value:
    source:
  temperature_series_available: yes_no
  pf_plot_window_V:
  plot_type_checked: ln_J_over_E_vs_sqrt_E

tat_high_field_diagnostic_priors:
  trap_energy_eV:
    value:
    source:
  electron_effective_mass_rel:
    value:
    source:
  hole_effective_mass_rel:
    value:
    source:
  depletion_or_field_width_cm:
    value:
    source:
  built_in_voltage_V:
    value:
    source:
  field_profile_source: measured_simulated_assumed
  temperature_series_available: yes_no

cqd_heterointerface_M8_priors:
  active_material:
  etl_material:
  htl_material:
  cqd_absorption_peak_nm:
  cqd_bandgap_eV:
  qd_center_distance_nm:
  qd_diameter_nm:
  electron_effective_mass_rel:
    value:
    source:
  barrier_height_phi_eV:
    value:
    source:
  built_in_potential_V:
    value:
    source:
  carrier_lifetime_s:
    value:
    source:
  interface_electron_density_cm3:
    value:
    source:
  rs_area_ohm_cm2:
    value:
    source:
  area_normalized_current: yes_no
  ligand_or_passivation:
  matched_control_devices:
  temperature_dependent_JV: yes_no

supporting_measurements:
  dark_JV_repeats:
  illuminated_JV:
  EQE_or_responsivity:
  temperature_dependent_JV:
  capacitance_voltage:
    file:
    frequency_Hz:
    voltage_column:
    raw_capacitance_column:
    smooth_capacitance_column:
    smooth_method:
    capacitance_unit:
    point_count:
    voltage_range_V:
    capacitance_quality: geometric_capacitance_plausible_or_diagnostic_shape_only
    epsilon_from_cv: candidate_rejected_for_now_missing
    field_width_from_cv: candidate_rejected_for_now_missing
    source:
    note:
  mobility_measurement:
  UPS_KPFM_work_function:
  thickness_measurement:
  SEM_AFM_GISAXS_GIWAXS:
  aging_or_stability:
```

## Minimum Sets

- M0-M3: raw JV points, current unit, voltage range/step, sign convention,
  temperature, active area if converting `A` to `A_per_cm2`, and a practical
  `fit_current_floor`.
- Clean M4: M0-M3 fields plus evidence of two forward semilog slopes.
- SCLC/TFL: M0-M3 fields plus active-layer thickness, permittivity, mobility,
  carrier type, and evidence of injection-limited single-carrier transport.
- Poole-Frenkel/TAT: M0-M3 fields plus thickness or field width, dielectric
  constants, trap/barrier priors, and preferably temperature-dependent JV.
- CQD heterointerface: M0-M3 fields plus PbS/ETL/HTL stack, area-normalized
  current, absorption peak or bandgap, QD spacing/effective mass, and priors or
  independent estimates for barrier height, built-in potential, lifetime, and
  interface carrier density.

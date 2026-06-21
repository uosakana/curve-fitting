# Literature Priors - Normal PbS CQD Photodiodes

This file is the cleaned literature-prior summary used to seed model bounds and
benchmark expectations for normal/upright PbS CQD photodiodes. Raw extraction
notes were removed from the workspace; this summary is the retained source.

Do not treat these records as raw JV datasets. They are priors and comparison
anchors. Actual fitting still requires measured voltage/current points.

## Source Tags

- `literature_reported`: explicitly reported in the paper/PDF.
- `derived_from_literature`: computed from reported values.
- `assumption`: working assumption, not a reported measurement.
- `not_reported`: searched but not found in the supplied main PDF.
- `not_in_supplied_pdf`: referenced in SI or table not available locally.

## Record 1 - Fang 2025 Surface-Reconstructed QD Normal PD

```yaml
record:
  record_id: Fang2025_INC2_SR_QD_normal_PD
  record_type: literature_prior
  status: draft_from_main_pdf

source:
  publication:
    title: Core-shell structure induced surface reconstruction of PbS quantum dots toward high-detectivity photodiodes
    doi: https://doi.org/10.1002/inc2.70003
    publication_window: 2025-04_to_2025-07
    source: literature_reported
  raw_jv_files: []

sample:
  sample_id: Fang2025_SR_QD_PD
  device_id: surface_reconstructed_PbS_QD_normal_PD
  measurement_date:
  dark_or_light: dark
  temperature_K:
    value: 298
    source: assumption_room_temperature
  instrument:
    value:
    source: not_reported

data:
  current_unit: A_per_cm2
  voltage_unit: V
  current_sign_convention: magnitude
  current_sign_note: Reverse-bias dark current is reported as positive magnitude; convert to negative internally.
  fit_current_floor:
    value:
    unit: A_per_cm2
    source:
    note: Not available from main PDF.
  spectral_noise:
    value: 1.85e-14
    unit: A_per_sqrtHz
    frequency_Hz: 1
    source: literature_reported

geometry:
  active_area_cm2:
    value: 0.04
    source: literature_reported
  active_layer_thickness_nm:
    value:
    source: not_reported
  active_layer_thickness_cm:
    value:
    source: not_reported
  contact_geometry: normal_vertical_sandwich

stack:
  substrate:
    material: ITO_glass
    treatment:
  bottom_electrode:
    material: ITO
  etl:
    material: ZnO
  active_layer:
    material: surface_reconstructed_PbS_PbX2_QDs
    ligand: PbI2_PbBr2_halide_exchange
    passivation: CdS_shell_induced_surface_reconstruction_then_halide_passivation
    absorption_peak_nm: 1320
    bandgap_eV: 0.94
    qd_diameter_nm: 4.20
    qd_center_distance_nm: 4.80
  htl:
    material: PbS_QD_HTL
    ligand: EDT_likely
  top_interlayer:
    material: MoOx
  top_electrode:
    material: Ag

baseline_M0_M3_priors:
  ideality_factor_n:
    value:
    source: not_in_supplied_pdf_Table_S4
  dark_saturation_current:
    expected:
    unit: A_per_cm2
    source: not_in_supplied_pdf_Table_S4
  shunt_resistance:
    expected: 2.6e6
    unit: ohm_cm2
    source: derived_from_literature_using_abs_V_over_total_J_at_minus_0p5V
    note: Apparent value only; do not use as fitted Rsh without raw JV.
  reported_dark_current_at_minus_0p5V:
    value: 1.92e-7
    unit: A_per_cm2
    source: literature_reported
  reverse_leakage_window_V: [-0.5]

cqd_heterointerface_M8_priors:
  active_material: SR_PbS_CQD
  etl_material: ZnO
  htl_material: PbS_QD_HTL
  cqd_absorption_peak_nm: 1320
  cqd_bandgap_eV: 0.94
  qd_center_distance_nm: 4.80
  qd_diameter_nm: 4.20
  carrier_lifetime_s:
    value: 1.264e-8
    source: literature_reported_TRPL_average_lifetime
  area_normalized_current: yes
  matched_control_devices:
    pristine_PbS_QD_PD:
      J_at_minus_0p5V_A_per_cm2: 6.47e-7
      Dstar_Jones_at_0V: 6.82e11
    SR_QD_PD:
      J_at_minus_0p5V_A_per_cm2: 1.92e-7
      EQE_percent_at_0V: 48
      Dstar_Jones_at_0V: 5.06e12
  temperature_dependent_JV: no
```

## Record 2 - Zhong 2026 HA Alkylamine Normal PD

```yaml
record:
  record_id: Zhong2026_ADMT_HA_normal_PD
  record_type: literature_prior
  status: draft_from_main_pdf

source:
  publication:
    title: Decoupling the Impact of Deep-Trap and Band-Tail States on PbS Quantum Dot Photodiodes
    doi: https://doi.org/10.1002/admt.70952
    publication_window: 2026-01_to_2026-03
    source: literature_reported
  raw_jv_files: []

sample:
  sample_id: Zhong2026_HA_PbS_CQD_PD
  device_id: HA_PbS_CQD_normal_PD
  measurement_date:
  dark_or_light: dark
  temperature_K:
    value: 298
    source: assumption_room_temperature
  instrument:
    value: Keithley_4200_for_JV_and_noise
    source: literature_reported

data:
  current_unit: A_per_cm2
  voltage_unit: V
  current_sign_convention: magnitude
  current_sign_note: Reverse-bias current is treated as magnitude in paper-level reports; use signed convention internally.
  fit_current_floor:
    value:
    unit: A_per_cm2
    source:
    note: Not available from main PDF.
  spectral_noise:
    value: 4.32e-13
    unit: A_per_sqrtHz
    frequency_Hz: 1
    source: literature_reported

geometry:
  active_area_cm2:
    value: 0.045
    source: literature_reported
  active_layer_thickness_nm:
    value:
    source: not_reported
  contact_geometry: normal_vertical_sandwich

stack:
  substrate:
    material: ITO_glass
    treatment: DI_water_isopropanol_acetone_ethanol_sonication_15min_each_then_UV_ozone_15min
  bottom_electrode:
    material: ITO
  etl:
    material: ZnO
    treatment: sol_gel_spin_3000rpm_30s_low_humidity_200degC_30min
  active_layer:
    material: HA_PbS_PbX2_QDs
    ligand: PbI2_PbBr2_halide_exchange_with_BA_HA_cosolvent_4_to_1
    passivation: HA_additive_coordinates_Pb_surface_sites
    qd_diameter_nm: 4.40
    qd_center_distance_nm: 4.61
  htl:
    material: PbS_EDT_CQDs
    ligand: EDT
  top_interlayer:
    material: MoOx
    thickness_nm: 10
  top_electrode:
    material: Ag
    thickness_nm: 100

baseline_M0_M3_priors:
  ideality_factor_n:
    value: 1.71
    source: literature_reported_main_text_dark_current_model
  dark_saturation_current:
    expected: 6.8e-7
    unit: A_per_cm2
    source: literature_reported_main_text_dark_current_model
  series_resistance:
    expected:
    source: not_in_supplied_pdf_Table_S6
  shunt_resistance:
    expected:
    source: not_in_supplied_pdf_Table_S6

cqd_heterointerface_M8_priors:
  active_material: HA_PbS_CQD
  etl_material: ZnO
  htl_material: PbS_EDT_CQDs
  qd_center_distance_nm: 4.61
  qd_diameter_nm: 4.40
  carrier_lifetime_s:
    value: 9.42e-9
    source: literature_reported_TRPL_average_lifetime
  area_normalized_current: yes
  matched_control_devices:
    Control_BA_DMF:
      J0_A_per_cm2: 1.74e-6
      ideality_factor_n: 1.76
      Dstar_Jones: 4.1e10
    PA:
      J0_A_per_cm2: 1.16e-6
      ideality_factor_n: 1.99
      Dstar_Jones: 5.6e10
    HA:
      J0_A_per_cm2: 6.8e-7
      ideality_factor_n: 1.71
      responsivity_A_per_W: 0.76
      EQE_percent: 72
      Dstar_Jones: 3.7e11
  temperature_dependent_JV: no
```

## Modeling Use

- Use these records to set broad priors and sanity-check fitted values for
  normal PbS CQD photodiodes.
- Do not use spectral noise density as `fit_current_floor` unless measurement
  bandwidth is known.
- Do not promote SCLC, PF, or TAT from diagnostic to physical conclusion without
  thickness, permittivity, mobility/trap priors, and preferably temperature or
  thickness-series data.

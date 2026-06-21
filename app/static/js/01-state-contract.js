/* ==========================================================================
   App state and contract defaults
   ========================================================================== */

const state = {
  uploadId: null,
  autoFitResult: null,
  displayResult: null,
  acceptedResult: null,
  selectedCandidateIndex: null,
  liveTimer: null,
  evaluateSeq: 0,
  fixedMeasured: null,
  plotScale: null,
  reviewCandidates: [],
  reviewOverlayEnabled: false,
  selectedFileName: "",
  assistantMessages: [],
  dataGrid: null,
  gridSelection: null,
  gridDragAnchor: null,
  gridDragging: false,
  gridDragMoved: false,
  gridSuppressClick: false,
  gridClickAnchor: null,
  userVoltageOverride: false,
  manualDraftResult: null,
  manualHistory: [],
  manualHistoryTimer: null,
  manualHistoryActiveId: null,
  chartMeta: {},
  reviewCandidatePreviewIndex: 0,
  txtImport: null,
  txtSelectedBlockIds: new Set(),
  txtScale: "log_abs",
  txtFitRangeBlockId: null,
  txtFitRangeTouched: false,
  selectedDeviceLayerId: null,
  deviceOrientation: "normal",
  flowStep: "home",
  flowReturnStep: null,
  deviceLayers: [
    { id: "moox_ag", role: "electrode", name: "MoOx-Ag", thickness_nm: "" },
    { id: "htl", role: "htl", name: "PbS-EDT", thickness_nm: "100", absorption_peak_nm: "" },
    { id: "absorber", role: "absorber", name: "PbS-ink", thickness_nm: "450", absorption_peak_nm: "1250" },
    { id: "etl", role: "etl", name: "ZnO", thickness_nm: "", absorption_peak_nm: "" },
    { id: "ito", role: "substrate", name: "ITO", thickness_nm: "", absorption_peak_nm: "" },
  ],
};

const deviceLayerPresets = {
  normal: [
    { id: "moox_ag", role: "electrode", name: "MoOx/Ag", thickness_nm: "" },
    { id: "htl", role: "htl", name: "PbS-EDT", thickness_nm: "100", absorption_peak_nm: "" },
    { id: "absorber", role: "absorber", name: "PbS-ink", thickness_nm: "450", absorption_peak_nm: "1250" },
    { id: "etl", role: "etl", name: "ZnO", thickness_nm: "", absorption_peak_nm: "" },
    { id: "ito", role: "substrate", name: "ITO", thickness_nm: "", absorption_peak_nm: "" },
  ],
  reverse: [
    { id: "ag", role: "electrode", name: "Ag", thickness_nm: "" },
    { id: "bcp", role: "modifier", name: "BCP", thickness_nm: "" },
    { id: "pcbm", role: "etl", name: "PCBM", thickness_nm: "" },
    { id: "c60", role: "etl", name: "C60", thickness_nm: "" },
    { id: "ink", role: "absorber", name: "Ink", thickness_nm: "", absorption_peak_nm: "1250" },
    { id: "edt", role: "htl", name: "EDT", thickness_nm: "" },
    { id: "niox", role: "htl", name: "NiOx", thickness_nm: "" },
    { id: "ito_reverse", role: "substrate", name: "ITO", thickness_nm: "" },
  ],
};

const colors = {
  measured: "#6BAED6",
  fitted: "#FB6A4A",
  ohmic: "#90BA48",
  diode: "#136AEE",
  recombination: "#7c3aed",
  diffusion: "#0f766e",
  nonohmic: "#DF42E3",
  extraCurrent: "#d8c4ff",
  grid: "#d8dee8",
  fineGrid: "#edf1f6",
  text: "#1f2933",
  muted: "#64748b",
};

const overlayColors = ["#9ff7ef", "#f5d28e", "#d8c4ff", "#b9f8d2"];

const componentColumns = [
  { key: "voltage", label: "Voltage(V)" },
  { key: "measured", label: "Measured_Current(A)" },
  { key: "fitted", label: "Fitted_Current(A)" },
  { key: "diode", label: "Diode_Current(A)" },
  { key: "ohmic", label: "Ohmic_Current(A)" },
  { key: "nonohmic", label: "Nonohmic_Current(A)" },
  { key: "relative_error", label: "Relative_Error(%)" },
];

const m4ComponentColumns = [
  { key: "recombination", label: "Recombination_Current(A)" },
  { key: "diffusion", label: "Diffusion_Current(A)" },
];

const extendedComponentColumns = [
  { key: "extra_current", label: "Extended_Branch_Current(A)" },
  { key: "extended_nonohmic_total", label: "Nonohmic_Plus_Extended_Current(A)" },
];

const requiredComponentKeys = ["voltage", "measured", "fitted", "diode", "ohmic", "nonohmic"];
const defaultVoltageWindow = { start: -0.5, end: 0.3, step: 0.01 };
let internalNProfileValues = "1.1, 1.3, 1.4, 1.7, 2.0";
let internalMProfileValues = "1.8, 2.0, 2.4, 2.8, 3.2";
let fitContract = null;

const $ = (id) => document.getElementById(id);

const productFlowSteps = [
  { id: "data", label: "Data", short: "D" },
  { id: "fit", label: "Fit", short: "F" },
  { id: "review", label: "Review", short: "R" },
  { id: "manual", label: "Manual", short: "M" },
  { id: "save", label: "Save", short: "S" },
];

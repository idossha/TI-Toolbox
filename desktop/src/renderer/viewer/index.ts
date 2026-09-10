/**
 * The viewer's public surface — what the Viewer page imports.
 *
 * Everything else in this directory is internal: a page that reaches past this file into the
 * channel is doing something the store should be doing instead. There is no Tetravox code here at
 * all any more — only the frame, the protocol types and the store (`docs/dev/HISTORY.md § 2026-09-02 (UX redesign)`
 * §4.3, revised: service boundary).
 */
export { TetravoxFrame, formatBytes } from "./TetravoxFrame";
export type { TetravoxFrameProps } from "./TetravoxFrame";
export { useViewerStore, HANDSHAKE_TIMEOUT_MS } from "./store";
export type { DatasetProgress, ViewerSpace, ViewerStatus } from "./store";
export {
  PROTOCOL_VERSION,
  acceptEmbedMessage,
  embedUrl,
  isEmbedMessage,
  normalizeLayers,
  normalizeLoadedDatasets,
} from "./protocol";
export type {
  Camera3D,
  CameraMessage,
  CameraPreset,
  EmbedDatasetRef,
  EmbedLayer,
  EmbedMessage,
  EmbedPoint,
  EmbedPointsLayer,
  EmbedViewSpec,
  HostMessage,
  LayoutKind,
  LoadedDataset,
  PickMessage,
  ProbeResult,
  ProbeRow,
  vec3,
  vec4,
} from "./protocol";

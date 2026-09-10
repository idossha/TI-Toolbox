/** Browser mode = the same bundle served by tit.server and opened in a normal browser. */
export const isElectron = typeof window !== "undefined" && window.tit !== undefined;

/** The bundled desktop home has no project server yet. */
export const isProjectHome = isElectron && window.location.protocol === "app:" && window.location.hostname === "launcher";

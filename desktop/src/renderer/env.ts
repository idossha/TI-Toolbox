/** Browser mode = the same bundle served by tit.server and opened in a normal browser. */
export const isElectron = typeof window !== "undefined" && window.tit !== undefined;

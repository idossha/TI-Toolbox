import { createContext, useContext } from "react";

/** Retained pages keep their state; only the visible page owns app-wide interactions. */
export const PageActivityContext = createContext(true);

export function usePageActive(): boolean {
  return useContext(PageActivityContext);
}

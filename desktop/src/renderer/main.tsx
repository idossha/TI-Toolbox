import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { initTheme } from "./app/theme/store";
import { App } from "./app/App";
import { ApiError } from "./api/client";
import "./index.css";
import "./ui/tokens.css";
import "./ui/base.css";
import "./ui/components.css";
import "./app/shell.css";

// Must run before the first React render: stamps the persisted theme onto <html data-theme> so
// there is no flash of the wrong palette (DESIGN.md §7).
initTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Catalog data changes only when jobs change (TODO section 4); never poll.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);

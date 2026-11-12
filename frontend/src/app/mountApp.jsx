import React from "react";
import { createRoot } from "react-dom/client";

import { ApiProvider } from "../api/ApiProvider";
import { createApiClient } from "../api/client";
import { App } from "./App";
import { RouterProvider } from "./router";

import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/shell.css";
import "../styles/ui.css";

export function mountApp(container, browser = window) {
  createRoot(container).render(
    <React.StrictMode>
      <ApiProvider client={createApiClient({ fetchImpl: browser.fetch.bind(browser) })}>
        <RouterProvider browser={browser}>
          <App />
        </RouterProvider>
      </ApiProvider>
    </React.StrictMode>,
  );
}

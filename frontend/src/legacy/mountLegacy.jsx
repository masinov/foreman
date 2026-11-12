import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { createDashboardServices } from "./api";
import "./styles.css";

// Mounts the pre-v7 application. Loaded only for paths under /dashboard/legacy,
// so neither its code nor its global stylesheet reaches the rebuilt pages.
export function mountLegacy(container, browser = window) {
  createRoot(container).render(
    <React.StrictMode>
      <App services={createDashboardServices()} browser={browser} />
    </React.StrictMode>,
  );
}

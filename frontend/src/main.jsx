import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { createDashboardServices } from "./api";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App services={createDashboardServices()} browser={window} />
  </React.StrictMode>,
);

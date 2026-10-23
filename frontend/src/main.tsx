import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { RuntimeGate } from "./runtime";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RuntimeGate>
      <App />
    </RuntimeGate>
  </React.StrictMode>,
);

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ServerApp from "./server/ServerApp";
import "./server/server.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ServerApp />
  </StrictMode>,
);


import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
import Theme from "./Theme.jsx";
import { GoogleOAuthProvider } from "@react-oauth/google";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Theme>
      <GoogleOAuthProvider clientId="832389663437-scnr2k6cv6u2gm72307viq25saoa9cua.apps.googleusercontent.com">
        <App />
      </GoogleOAuthProvider>
    </Theme>
  </StrictMode>,
);

import React, { useEffect, useState } from "react";

import { checkToken } from "../api/access";
import { useApiClient, useDataRefresh } from "../api/ApiProvider";
import { errorSentence } from "../api/client";
import { writeDashboardToken } from "../api/token";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Logo } from "../ui/Logo";

/**
 * The page a person sees when the server wants an access token and this
 * browser has none it accepts. The token is tried first; only one the server
 * accepts is kept.
 */
function SignInPage({ onSignedIn }) {
  const client = useApiClient();
  const [token, setToken] = useState("");
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) {
      setError("Paste the access token.");
      return;
    }
    setChecking(true);
    setError(null);
    try {
      await checkToken(client, candidate);
    } catch (caught) {
      setChecking(false);
      setError(caught?.status === 401 ? "The server did not accept that token." : errorSentence(caught));
      return;
    }
    if (!writeDashboardToken(candidate)) {
      setChecking(false);
      setError("This browser would not keep the token. Allow site data for this address and try again.");
      return;
    }
    onSignedIn();
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__inner">
          <span className="topbar__home">
            <Logo />
          </span>
        </div>
      </header>
      <main className="page" id="main">
        <div className="sign-in">
        <h1 className="page-title">Sign in</h1>
        <p className="sign-in__text">
          This dashboard asks for an access token. It is the one the server was started with (
          <span className="mono">foreman dashboard --token</span>, or{" "}
          <span className="mono">FOREMAN_DASHBOARD_TOKEN</span>); whoever runs the server has it.
        </p>
        <form className="sign-in__form" onSubmit={submit} noValidate>
          <Field
            label="Access token"
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(event) => {
              setToken(event.target.value);
              setError(null);
            }}
            error={error}
            hint="Kept in this browser only. Sign out, in the menu under your name, forgets it."
            required
            autoFocus
          />
          <div>
            <Button type="submit" disabled={checking}>
              {checking ? "Checking…" : "Sign in"}
            </Button>
          </div>
        </form>
        </div>
      </main>
    </div>
  );
}

/**
 * Shows the application until the server refuses a request for want of a
 * token it accepts, then the sign-in page in its place. That covers the first
 * visit and a token that stops being accepted while the dashboard is open.
 */
export function SignInGate({ children }) {
  const client = useApiClient();
  const { refresh } = useDataRefresh();
  const [locked, setLocked] = useState(false);

  useEffect(() => client.onUnauthorized(() => setLocked(true)), [client]);

  if (!locked) return children;
  return (
    <SignInPage
      onSignedIn={() => {
        setLocked(false);
        refresh();
      }}
    />
  );
}

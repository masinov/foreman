import React, { useEffect, useState } from "react";

import { createToken, getSession, listTokens, revokeToken } from "../../api/access";
import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { formatDay } from "../../ui/format";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { ConfirmDialog } from "./ConfirmDialog";
import { CopyButton } from "./CopyButton";
import { ProjectSelect } from "./ProjectSelect";

function NewTokenDialog({ open, projects, scopes, onClose, onCreated }) {
  const client = useApiClient();
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState([]);
  const [nameError, setNameError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setProjectId(projects[0]?.id ?? "");
    setName("");
    setChosen(scopes.includes("intake") ? ["intake"] : scopes.slice(0, 1));
    setNameError(null);
    setError(null);
    // Only when the dialog opens: the lists arriving later must not wipe typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    if (!name.trim()) {
      setNameError("A token needs a name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onCreated(await createToken(client, projectId, { name: name.trim(), scopes: chosen }));
    } catch (caught) {
      if (caught.field === "name") setNameError(errorSentence(caught));
      else setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="New token"
      description="A token lets another system file work in one project. Its secret is shown once, when you create it."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        {projects.length === 0 ? (
          <p className="notice">There are no projects yet. A token belongs to a project.</p>
        ) : (
          <ProjectSelect projects={projects} value={projectId} onChange={setProjectId} />
        )}
        <Field
          label="Name"
          hint="What holds this token, for example pagerduty or ci. It is recorded on every task the token files."
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setNameError(null);
          }}
          error={nameError}
          required
          data-autofocus
        />
        <fieldset className="scopes">
          <legend className="field__label">Scopes</legend>
          {scopes.map((scope) => (
            <label key={scope} className="scopes__option">
              <input
                type="checkbox"
                className="checkbox"
                checked={chosen.includes(scope)}
                onChange={(event) =>
                  setChosen((current) => (event.target.checked ? [...current, scope] : current.filter((s) => s !== scope)))
                }
              />
              <Mono>{scope}</Mono>
            </label>
          ))}
        </fieldset>
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving || projects.length === 0}>
            {saving ? "Creating…" : "Create token"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/**
 * The secret of a token just created. It lives in this component's props
 * only: closing the dialog drops it, and nothing stores it.
 */
function SecretDialog({ token, onClose }) {
  return (
    <Dialog
      open={Boolean(token)}
      title="Copy the secret now"
      description={
        token ? `This is the only time the secret of ${token.name} is shown. Foreman keeps only a hash of it.` : ""
      }
      onClose={onClose}
      footer={<Button onClick={onClose}>Done</Button>}
    >
      {token ? (
        <div className="secret">
          <Mono className="secret__value" data-autofocus tabIndex={0}>
            {token.secret}
          </Mono>
          <CopyButton text={token.secret} label="Copy secret" />
          <p className="notice">If it is lost, revoke this token and create another.</p>
        </div>
      ) : null}
    </Dialog>
  );
}

/** Access: who can open this dashboard and act in it. */
export function AccessSection() {
  const client = useApiClient();
  const tokens = useResource(["tokens"], listTokens);
  const session = useResource(["session"], getSession);
  const workspace = useResource(["workspace"], getWorkspace);
  const placeholder = useDelayedFlag(tokens.loading && !tokens.data);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [revoking, setRevoking] = useState(null);
  const projects = workspace.data?.projects ?? [];

  return (
    <section className="settings-block" aria-labelledby="access-title">
      <SectionHeading
        id="access-title"
        title="Access"
        note="Who can open this dashboard and act in it."
        actions={<Button onClick={() => setCreating(true)}>New token</Button>}
      />
      {tokens.error ? (
        <p className="notice notice--error" role="alert">
          {tokens.error}
        </p>
      ) : null}
      {tokens.data && tokens.data.tokens.length === 0 ? (
        <p className="empty">No tokens yet. Create one to let another system file work in a project.</p>
      ) : (
        <Table
          caption="API tokens"
          rows={tokens.data?.tokens ?? []}
          placeholderRows={placeholder ? 2 : null}
          columns={[
            {
              key: "name",
              header: "Access token",
              render: (token) => (
                <span className={token.active ? undefined : "settings-block__revoked"}>
                  {token.name}
                  <span className="settings-block__aside"> · {token.project_name}</span>
                </span>
              ),
            },
            {
              key: "scopes",
              header: "Scopes",
              render: (token) => token.scopes.map((scope) => <Mono key={scope}>{scope}</Mono>),
            },
            { key: "created", header: "Created", render: (token) => formatDay(token.created_at) },
            {
              key: "used",
              header: "Last used",
              render: (token) => (token.last_used_at ? formatDay(token.last_used_at) : "Never"),
            },
            {
              key: "revoke",
              header: <span className="visually-hidden">Actions</span>,
              className: "settings-block__action",
              render: (token) =>
                token.active ? (
                  <Button inRow aria-label={`Revoke ${token.name}`} onClick={() => setRevoking(token)}>
                    Revoke
                  </Button>
                ) : (
                  <span className="settings-block__revoked">Revoked {formatDay(token.revoked_at)}</span>
                ),
            },
          ]}
        />
      )}
      <p className="settings-block__line">
        {session.data && session.data.identity_provider
          ? `Identity provider: ${session.data.identity_provider.name}. `
          : "Identity provider: none configured. "}
        <span className="settings-block__aside">
          {session.data && !session.data.identity_provider
            ? "People are identified by the token they use, and that name is recorded on every decision."
            : ""}
        </span>
      </p>

      <NewTokenDialog
        open={creating}
        projects={projects}
        scopes={tokens.data?.scopes ?? []}
        onClose={() => setCreating(false)}
        onCreated={(token) => {
          setCreating(false);
          setCreated(token);
          tokens.reload();
        }}
      />
      <SecretDialog token={created} onClose={() => setCreated(null)} />
      <ConfirmDialog
        open={Boolean(revoking)}
        title={revoking ? `Revoke ${revoking.name}?` : "Revoke token"}
        description="Whatever uses this token stops being able to file work. This cannot be undone; create another token to replace it."
        confirmLabel="Revoke token"
        busyLabel="Revoking…"
        onClose={() => setRevoking(null)}
        onConfirm={async () => {
          await revokeToken(client, revoking.id);
          setRevoking(null);
          tokens.reload();
        }}
      />
    </section>
  );
}

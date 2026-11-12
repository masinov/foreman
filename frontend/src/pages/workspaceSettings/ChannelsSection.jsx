import React, { useEffect, useState } from "react";

import { createChannel, deleteChannel, listChannels } from "../../api/access";
import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { ConfirmDialog } from "./ConfirmDialog";
import { ProjectSelect } from "./ProjectSelect";

function AddChannelDialog({ open, projects, onClose, onAdded }) {
  const client = useApiClient();
  const [projectId, setProjectId] = useState("");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [errors, setErrors] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setProjectId(projects[0]?.id ?? "");
    setName("");
    setUrl("");
    setSecretEnv("");
    setErrors({});
    setError(null);
    // Only when the dialog opens: the list arriving later must not wipe typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function submit(event) {
    event.preventDefault();
    const missing = {};
    if (!name.trim()) missing.name = "A channel needs a name.";
    if (!url.trim()) missing.url = "A channel needs an address.";
    if (Object.keys(missing).length) {
      setErrors(missing);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      onAdded(await createChannel(client, projectId, { name: name.trim(), url: url.trim(), secretEnv: secretEnv.trim() }));
    } catch (caught) {
      if (caught.field === "name" || caught.field === "url") setErrors({ [caught.field]: errorSentence(caught) });
      else setError(errorSentence(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Add channel"
      description="Foreman sends a JSON message to this address. The project's notification setting decides what is sent."
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit} noValidate>
        {projects.length === 0 ? (
          <p className="notice">There are no projects yet. A channel belongs to a project.</p>
        ) : (
          <ProjectSelect projects={projects} value={projectId} onChange={setProjectId} />
        )}
        <Field
          label="Name"
          hint="For example ops-channel. Each name is used once per project."
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setErrors((current) => ({ ...current, name: null }));
          }}
          error={errors.name}
          required
          data-autofocus
        />
        <Field
          label="Address"
          hint="An http:// or https:// URL that accepts a POST."
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
            setErrors((current) => ({ ...current, url: null }));
          }}
          error={errors.url}
          required
        />
        <Field
          label="Signing key variable"
          hint="Optional. The name of an environment variable on this machine that holds the key each message is signed with. The key itself is never stored."
          value={secretEnv}
          onChange={(event) => setSecretEnv(event.target.value)}
        />
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
            {saving ? "Adding…" : "Add channel"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

/** Notification channels: where Foreman sends a message. */
export function ChannelsSection() {
  const client = useApiClient();
  const channels = useResource(["notification-channels"], listChannels);
  const workspace = useResource(["workspace"], getWorkspace);
  const placeholder = useDelayedFlag(channels.loading && !channels.data);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState(null);

  return (
    <section className="settings-block" aria-labelledby="channels-title">
      <SectionHeading
        id="channels-title"
        title="Notification channels"
        actions={<Button onClick={() => setAdding(true)}>Add channel</Button>}
      />
      {channels.error ? (
        <p className="notice notice--error" role="alert">
          {channels.error}
        </p>
      ) : null}
      {channels.data && channels.data.channels.length === 0 ? (
        <p className="empty">
          No channels yet.{" "}
          <span className="settings-block__aside">
            A channel is where Foreman sends a message; each project chooses what to send.
          </span>
        </p>
      ) : (
        <Table
          caption="Notification channels"
          rows={channels.data?.channels ?? []}
          placeholderRows={placeholder ? 2 : null}
          columns={[
            { key: "name", header: "Channel", render: (channel) => channel.name },
            { key: "project", header: "Project", render: (channel) => channel.project_name },
            { key: "kind", header: "Kind", render: (channel) => humanize(channel.kind) },
            {
              key: "target",
              header: "Address",
              render: (channel) => (
                <>
                  <Mono>{channel.target}</Mono>
                  {channel.signed ? <span className="settings-block__aside"> · signed</span> : null}
                  {channel.enabled ? null : <span className="settings-block__aside"> · off</span>}
                </>
              ),
            },
            {
              key: "remove",
              header: <span className="visually-hidden">Actions</span>,
              className: "settings-block__action",
              render: (channel) => (
                <Button inRow aria-label={`Remove ${channel.name}`} onClick={() => setRemoving(channel)}>
                  Remove
                </Button>
              ),
            },
          ]}
        />
      )}
      <AddChannelDialog
        open={adding}
        projects={workspace.data?.projects ?? []}
        onClose={() => setAdding(false)}
        onAdded={() => {
          setAdding(false);
          channels.reload();
        }}
      />
      <ConfirmDialog
        open={Boolean(removing)}
        title={removing ? `Remove ${removing.name}?` : "Remove channel"}
        description="Messages queued for this channel and its delivery history are removed with it."
        confirmLabel="Remove channel"
        busyLabel="Removing…"
        onClose={() => setRemoving(null)}
        onConfirm={async () => {
          await deleteChannel(client, removing.id);
          setRemoving(null);
          channels.reload();
        }}
      />
    </section>
  );
}

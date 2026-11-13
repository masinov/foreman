import React, { useEffect, useMemo, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { ApiError, errorSentence } from "../../api/client";
import { getProjectSettings, updateProjectSettings } from "../../api/projects";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { PolicyRules } from "./PolicyRules";
import { ReadOnlyRow, SettingRow, SettingsSection } from "./SettingRow";
import { changedKeys, changesOf, sourceOf, toDraft } from "./settingsForm";
import { WorkingCopies } from "./WorkingCopies";
import { DECIDERS, machineRows, NOTIFICATIONS } from "./settingsWords";

function Choice({ options, value, onChange, ...controlProps }) {
  return (
    <select className="field__input" value={value} onChange={(event) => onChange(event.target.value)} {...controlProps}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.word}
        </option>
      ))}
    </select>
  );
}

function Text({ value, onChange, narrow = true, wide = false, ...controlProps }) {
  const size = wide ? " setting-row__input--wide" : narrow ? " setting-row__input--narrow" : "";
  return (
    <input
      className={`field__input${size}`}
      type="text"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      {...controlProps}
    />
  );
}

const TASK_PICKING = [
  { value: "directed", word: "Off" },
  { value: "autonomous", word: "On" },
];

function MachineValue({ value, empty }) {
  return value ? <Mono>{value}</Mono> : <span className="setting-row__none">{empty}</span>;
}

/**
 * The form. `initial` is what was read; the draft is what is typed. Save sends
 * only the settings that changed; a refusal from the API is shown beside the
 * setting it names, and what could not be tied to one shows beside Save.
 */
function GeneralForm({ projectId, settings, onSaved }) {
  const client = useApiClient();
  // The page reads its data again whenever the project changes (app/useLiveData).
  // The draft starts over only when the values read are different, never
  // because the same values arrived again, so typing is not wiped.
  const read = JSON.stringify(toDraft(sourceOf(settings)));
  const initial = useMemo(() => JSON.parse(read), [read]);
  const [draft, setDraft] = useState(initial);
  const [errors, setErrors] = useState({});
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);

  // What was read changed (after a save, or the page was read again).
  useEffect(() => {
    setDraft(initial);
    setErrors({});
  }, [initial]);

  const dirty = changedKeys(initial, draft).length > 0;

  function set(key, value) {
    setDraft((all) => ({ ...all, [key]: value }));
    setErrors(({ [key]: _cleared, ...rest }) => rest);
    setNotice(null);
  }

  function discard() {
    setDraft(initial);
    setErrors({});
    setNotice(null);
  }

  async function save(event) {
    event.preventDefault();
    const result = changesOf(initial, draft);
    if (result.errors) {
      setErrors(result.errors);
      setNotice({ error: true, text: "Some values need another look." });
      return;
    }
    setSaving(true);
    setErrors({});
    setNotice(null);
    try {
      await updateProjectSettings(client, projectId, { settings: result.settings, project: result.project });
      setNotice({ error: false, text: "Saved." });
      onSaved();
    } catch (error) {
      if (error instanceof ApiError && error.field && error.field in draft) {
        setErrors({ [error.field]: error.message });
        setNotice({ error: true, text: "Nothing was saved." });
      } else {
        setNotice({ error: true, text: errorSentence(error) });
      }
    } finally {
      setSaving(false);
    }
  }

  const effective = settings.effective;
  const machine = machineRows(settings.host_level_settings, effective);

  function row({ key, label, hint, render }) {
    return (
      <SettingRow key={key} label={label} hint={hint} error={errors[key]}>
        {(controlProps) => render(controlProps)}
      </SettingRow>
    );
  }

  function choiceRow(key, label, options, hint) {
    return row({
      key,
      label,
      hint,
      render: (controlProps) => <Choice options={options} value={draft[key]} onChange={(value) => set(key, value)} {...controlProps} />,
    });
  }

  function textRow(key, label, hint, extra = {}) {
    return row({
      key,
      label,
      hint,
      render: (controlProps) => <Text value={draft[key]} onChange={(value) => set(key, value)} {...extra} {...controlProps} />,
    });
  }

  return (
    <form className="settings" onSubmit={save} onReset={(event) => { event.preventDefault(); discard(); }} noValidate>
      <SettingsSection
        id="settings-who"
        title="Who decides"
        note="Which decisions come to a person. Everything else in Needs you follows from this."
      >
        {choiceRow("triage", "Accept filed work", DECIDERS, "Work filed by another system or an agent")}
        {choiceRow("plan_approval", "Approve plans", DECIDERS, "Before development starts")}
        {choiceRow("merge_approval", "Approve merges", DECIDERS, "After tests and review")}
        <SettingRow label="Exceptions" error={errors.policy_rules} group>
          {(controlProps) => (
            <PolicyRules
              rules={draft.policy_rules}
              onChange={(rules) => set("policy_rules", rules)}
              describedBy={controlProps["aria-describedby"]}
            />
          )}
        </SettingRow>
      </SettingsSection>

      <SettingsSection id="settings-pick" title="Task picking">
        {choiceRow(
          "task_selection_mode",
          "Foreman picks its own tasks",
          TASK_PICKING,
          draft.task_selection_mode === "autonomous"
            ? "On: it may create tasks of its own in the active sprint"
            : "Off: it runs only the tasks planned into the active sprint",
        )}
        {textRow("max_autonomous_tasks", "At most, per sprint", "tasks it may add on its own")}
      </SettingsSection>

      <SettingsSection id="settings-limits" title="Limits" note="When one is reached the engine stops and says which.">
        {textRow("cost_limit_per_task_usd", "Spend per task", "USD. Empty: no limit", { inputMode: "decimal" })}
        {textRow("cost_limit_per_sprint_usd", "Spend per sprint", "USD. Empty: no limit", { inputMode: "decimal" })}
        {textRow("time_limit_per_task_ms", "Time per task", "minutes. Empty: no limit", { inputMode: "decimal" })}
        {textRow("max_step_visits", "Attempts at one step", "then the task is parked and appears in Needs you", { inputMode: "numeric" })}
        {textRow("max_live_worktrees", "Tasks in progress at once", "each has its own working copy. Empty: no limit", { inputMode: "numeric" })}
      </SettingsSection>

      <SettingsSection id="settings-models" title="Models">
        {textRow("default_model", "Default model", "A role can name its own. Empty: the runner's default", { narrow: false })}
        {textRow("meta_agent_model", "Manager model", "Empty: the runner's default", { narrow: false })}
      </SettingsSection>

      <SettingsSection id="settings-tests" title="Tests">
        <ReadOnlyRow label="Test command" hint="Changed from a terminal">
          <MachineValue value={effective.test_command} empty="Not set" />
        </ReadOnlyRow>
        {textRow("test_timeout_seconds", "Give up after", "minutes. Empty: never", { inputMode: "decimal" })}
      </SettingsSection>

      <SettingsSection id="settings-notify" title="Notifications and history">
        {choiceRow("notification", "Tell me", NOTIFICATIONS, "Channels are set up in workspace settings")}
        {textRow("event_retention_days", "Keep events", "days. Empty: forever", { inputMode: "numeric" })}
        {textRow("run_retention_days", "Keep runs", "days. Empty: forever", { inputMode: "numeric" })}
        {textRow("prompt_retention_days", "Keep prompts", "days. Empty: forever", { inputMode: "numeric" })}
      </SettingsSection>

      <SettingsSection
        id="settings-advanced"
        title="Advanced"
        note="Rarely changed. Each has a default that suits most projects."
      >
        {textRow("default_branch", "Merges land on", "the branch finished tasks are merged into", { narrow: false })}
        {textRow("spec_path", "Specification", "A file in the repository that agents are pointed to. Empty: none", { wide: true })}
        {textRow("review_diff_max_chars", "Reviewer reads at most", "characters of a change; a longer one is cut and the reviewer is told", { inputMode: "numeric" })}
        {textRow("judge_model", "Criteria judge", "The model that checks acceptance criteria. Empty: they are not judged", { narrow: false })}
        {textRow("judge_max_diff_chars", "Judge reads at most", "characters of a change", { inputMode: "numeric" })}
      </SettingsSection>

      <WorkingCopies projectId={projectId} />

      <SettingsSection
        id="settings-machine"
        title="This machine"
        note={
          <>
            Shown here, changed from a terminal: <Mono>foreman config {projectId} --set key=value</Mono>
          </>
        }
      >
        {machine.map((entry) => (
          <ReadOnlyRow key={entry.key} label={entry.label}>
            <MachineValue value={entry.value} empty={entry.empty} />
          </ReadOnlyRow>
        ))}
      </SettingsSection>

      <div className="settings__actions">
        <Button type="submit" variant="default" disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
        <Button type="reset" variant="quiet" disabled={!dirty || saving}>
          Discard
        </Button>
        {notice ? (
          <span className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
            {notice.text}
          </span>
        ) : null}
      </div>
    </form>
  );
}

/** /dashboard/projects/{id}/settings: the General tab. */
export function GeneralTab({ projectId }) {
  const settings = useResource(["project-settings", projectId], (client, options) =>
    getProjectSettings(client, projectId, options),
  );
  if (settings.error && !settings.data) {
    return (
      <p className="notice notice--error" role="alert">
        {settings.error}
      </p>
    );
  }
  if (!settings.data) return <p className="notice">Loading settings…</p>;
  return <GeneralForm projectId={projectId} settings={settings.data} onSaved={settings.reload} />;
}

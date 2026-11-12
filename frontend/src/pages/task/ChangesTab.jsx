import React, { useEffect, useState } from "react";

import { getFileDiff } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Icon } from "../../ui/Icon";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { shortSha } from "../../ui/format";
import { parseDiff } from "./diff";

const STATUS_WORDS = { added: "added", deleted: "deleted", renamed: "renamed", modified: "" };

// Folders are offered as a way to narrow the list once it is long enough to
// need one.
export const FOLDERS_FROM = 10;

/**
 * The files under `dir` (a path prefix ending in "/", or "" for all), and the
 * folders directly inside it with what changed in each.
 */
export function scopeOf(files, dir) {
  const inside = files.filter((file) => file.path.startsWith(dir));
  const folders = new Map();
  for (const file of inside) {
    const rest = file.path.slice(dir.length);
    const slash = rest.indexOf("/");
    if (slash === -1) continue;
    const name = rest.slice(0, slash);
    const folder = folders.get(name) ?? { name, path: `${dir}${name}/`, files: 0, added: 0, deleted: 0 };
    folder.files += 1;
    folder.added += file.added || 0;
    folder.deleted += file.deleted || 0;
    folders.set(name, folder);
  }
  return { files: inside, folders: [...folders.values()] };
}

/** "a/b/" as the steps of a breadcrumb: [{ name: "a", path: "a/" }, { name: "b", path: "a/b/" }]. */
function stepsOf(dir) {
  const names = dir.split("/").filter(Boolean);
  return names.map((name, index) => ({ name, path: `${names.slice(0, index + 1).join("/")}/` }));
}

function FolderCrumbs({ dir, onPick }) {
  const steps = stepsOf(dir);
  return (
    <nav className="folder-crumbs" aria-label="Folder">
      <ol className="folder-crumbs__list">
        <li className="folder-crumbs__item">
          {dir ? (
            <button type="button" className="folder-crumbs__step" onClick={() => onPick("")}>
              All files
            </button>
          ) : (
            <span aria-current="true">All files</span>
          )}
        </li>
        {steps.map((step, index) => (
          <li className="folder-crumbs__item" key={step.path}>
            {index === steps.length - 1 ? (
              <Mono aria-current="true">{step.name}</Mono>
            ) : (
              <button type="button" className="folder-crumbs__step" onClick={() => onPick(step.path)}>
                <Mono>{step.name}</Mono>
              </button>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function DiffLines({ rows }) {
  return (
    <div className="diff-scroll">
      <table className="diff">
        <caption className="visually-hidden">Lines changed. A plus sign marks an added line, a minus sign a removed one.</caption>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className={`diff__line diff__line--${row.kind}`}>
              <td className="diff__number">{row.oldLine ?? ""}</td>
              <td className="diff__number">{row.newLine ?? ""}</td>
              <td className="diff__sign">{row.sign}</td>
              <td className="diff__text">{row.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// The diff is read again when the branch's head moves, not on every event of
// a running task: the lines only change when a commit does.
function FileDiff({ taskId, file, head }) {
  const diff = useResource(["task-diff", taskId, file.path, head], (client, options) =>
    getFileDiff(client, taskId, file.path, options),
  );
  const rows = diff.data ? parseDiff(diff.data.diff) : [];
  return (
    <section className="task-section" aria-labelledby="task-diff">
      <SectionHeading
        id="task-diff"
        title={<Mono>{file.path}</Mono>}
        note={file.old_path ? `renamed from ${file.old_path}` : null}
      />
      {diff.error ? (
        <p className="notice notice--error" role="alert">
          {diff.error}
        </p>
      ) : null}
      {diff.data?.truncated ? (
        <p className="notice" role="status">
          This diff is {diff.data.total_chars.toLocaleString("en-US")} characters long; the first{" "}
          {diff.data.cap_chars.toLocaleString("en-US")} are shown.
        </p>
      ) : null}
      {diff.data && rows.length === 0 ? (
        <p className="empty">
          {file.binary ? "A binary file. There are no lines to show." : "No line changed in this file; only its name or mode did."}
        </p>
      ) : null}
      {rows.length ? <DiffLines rows={rows} /> : null}
    </section>
  );
}

/**
 * Changes: the totals, the files the branch changed, and the selected file's
 * diff. The first file is selected until another is picked.
 */
export function ChangesTab({ task, changes }) {
  const [picked, setPicked] = useState(null);
  const [dir, setDir] = useState("");
  const data = changes.data;
  // The first file is picked once and then stays picked. While an agent is
  // still committing, the list changes under the reader; what they are
  // looking at must not.
  const first = data?.files?.[0]?.path ?? null;
  useEffect(() => {
    if (picked === null && first !== null) setPicked(first);
  }, [picked, first]);
  if (!data) {
    return changes.error ? (
      <p className="notice notice--error" role="alert">
        {changes.error}
      </p>
    ) : null;
  }
  if (data.files.length === 0) {
    return <p className="empty">{data.empty_reason || "The branch changes no file yet."}</p>;
  }
  const selected = data.files.find((file) => file.path === picked) ?? data.files[0];
  const scope = scopeOf(data.files, dir);
  // A folder that no longer has a changed file in it falls back to everything.
  const shown = scope.files.length ? scope : scopeOf(data.files, "");
  const here = scope.files.length ? dir : "";
  const offerFolders = shown.folders.length > 0 && (here !== "" || data.files.length >= FOLDERS_FROM);
  const base = data.base?.branch;
  const head = shortSha(data.head?.sha);

  const columns = [
    {
      key: "file",
      header: "File",
      render: (file) => (
        <button
          type="button"
          className="file-pick"
          aria-pressed={file === selected}
          onClick={() => setPicked(file.path)}
        >
          <Mono>{file.path.slice(here.length)}</Mono>
          {STATUS_WORDS[file.status] ? <span className="quiet"> {STATUS_WORDS[file.status]}</span> : null}
        </button>
      ),
    },
    {
      key: "lines",
      header: "Lines changed",
      className: "task-files__lines",
      render: (file) =>
        file.binary ? (
          <span className="quiet">binary</span>
        ) : (
          <Mono>
            <span className="tone-passed">+{file.added}</span> <span className="tone-failed">−{file.deleted}</span>
          </Mono>
        ),
    },
  ];

  return (
    <div className="task-changes">
      <section className="task-section task-changes__files" aria-labelledby="task-files">
        <SectionHeading
          id="task-files"
          title="Files"
          count={data.files.length}
          note={
            <Mono>
              <span className="tone-passed">+{data.totals?.added ?? 0}</span>{" "}
              <span className="tone-failed">−{data.totals?.deleted ?? 0}</span>
            </Mono>
          }
        />
        {head && base ? (
          <p className="quiet task-changes__compared">
            <Mono>{head}</Mono> compared with {base}
          </p>
        ) : null}
        {offerFolders || here ? <FolderCrumbs dir={here} onPick={setDir} /> : null}
        <div className="task-changes__list">
          {offerFolders ? (
            <ul className="folder-list" aria-label="Folders">
              {shown.folders.map((folder) => (
                <li key={folder.path}>
                  <button type="button" className="folder-pick" onClick={() => setDir(folder.path)}>
                    <Icon name="folder" />
                    <Mono>{folder.name}</Mono>
                    <span className="quiet">{folder.files === 1 ? "1 file" : `${folder.files} files`}</span>
                    <Mono className="folder-pick__lines">
                      <span className="tone-passed">+{folder.added}</span> <span className="tone-failed">−{folder.deleted}</span>
                    </Mono>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <Table
            caption="Files changed"
            columns={columns}
            rows={shown.files}
            rowKey={(file) => file.path}
            selected={(file) => file === selected}
            hideHeader
          />
        </div>
      </section>
      <div className="task-changes__diff">
        <FileDiff key={selected.path} taskId={task.id} file={selected} head={data.head?.sha ?? null} />
      </div>
    </div>
  );
}


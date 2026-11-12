import React, { useState } from "react";

import { getFileDiff } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { shortSha } from "../../ui/format";
import { parseDiff } from "./diff";

const STATUS_WORDS = { added: "added", deleted: "deleted", renamed: "renamed", modified: "" };

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

function FileDiff({ taskId, file, revision }) {
  const diff = useResource(["task-diff", taskId, file.path, revision], (client, options) =>
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
export function ChangesTab({ task, changes, revision }) {
  const [picked, setPicked] = useState(null);
  const data = changes.data;
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
          <Mono>{file.path}</Mono>
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
        <div className="task-changes__list">
          <Table
            caption="Files changed"
            columns={columns}
            rows={data.files}
            rowKey={(file) => file.path}
            selected={(file) => file === selected}
            hideHeader
          />
        </div>
      </section>
      <div className="task-changes__diff">
        <FileDiff key={selected.path} taskId={task.id} file={selected} revision={revision} />
      </div>
    </div>
  );
}


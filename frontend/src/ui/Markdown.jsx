import React from "react";

// What agents write is Markdown: paragraphs, lists ("- ", "* ", "1. ",
// nested by indentation), headings, fenced code, **bold** and `code`. This
// reads that much into elements (never into HTML), so their words show as
// they meant them; anything else shows as written.

const BULLET = /^(\s*)(?:[-*]|(\d+)[.)])\s+(.*)$/;
const FENCE = /^\s*```/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

/** `code` and **bold** inside one line of text. */
function inline(text, keyPrefix) {
  const parts = [];
  const pattern = /`([^`]+)`|\*\*(.+?)\*\*/g;
  let last = 0;
  let match;
  let index = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const key = `${keyPrefix}-${index++}`;
    // Bold can hold code ("**Tests in `x.py`:**"); code holds nothing but itself.
    parts.push(match[1] !== undefined ? <code key={key}>{match[1]}</code> : <strong key={key}>{inline(match[2], key)}</strong>);
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** The blocks of a text: paragraphs, headings, code, and list items with their depth. */
export function blocksOf(text) {
  const blocks = [];
  let paragraph = [];
  let code = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
    paragraph = [];
  };
  for (const line of String(text ?? "").split("\n")) {
    if (code) {
      if (FENCE.test(line)) {
        blocks.push({ kind: "code", text: code.join("\n") });
        code = null;
      } else code.push(line);
      continue;
    }
    if (FENCE.test(line)) {
      flush();
      code = [];
      continue;
    }
    const bullet = line.match(BULLET);
    const heading = line.match(HEADING);
    if (bullet) {
      flush();
      blocks.push({ kind: "item", depth: Math.floor(bullet[1].length / 2), ordered: bullet[2] !== undefined, text: bullet[3] });
    } else if (heading) {
      flush();
      blocks.push({ kind: "heading", text: heading[1] });
    } else if (!line.trim()) {
      flush();
    } else if (!paragraph.length && blocks.length && blocks[blocks.length - 1].kind === "item" && /^\s/.test(line)) {
      // A wrapped line of a list item continues it.
      blocks[blocks.length - 1].text += ` ${line.trim()}`;
    } else {
      paragraph.push(line.trim());
    }
  }
  if (code) blocks.push({ kind: "code", text: code.join("\n") });
  flush();
  return blocks;
}

/** Consecutive list items as nested lists: a deeper item belongs to the item above it. */
function list(items, start, depth, key) {
  const entries = [];
  let index = start;
  const ordered = items[start].ordered;
  while (index < items.length && items[index].depth >= depth) {
    const item = items[index];
    if (item.depth > depth && entries.length) {
      const [nested, next] = list(items, index, item.depth, `${key}-${index}`);
      entries[entries.length - 1].nested.push(nested);
      index = next;
      continue;
    }
    entries.push({ index, text: item.text, nested: [] });
    index += 1;
  }
  const Tag = ordered ? "ol" : "ul";
  const element = (
    <Tag key={key}>
      {entries.map((entry) => (
        <li key={entry.index}>
          {inline(entry.text, `${key}-${entry.index}`)}
          {entry.nested}
        </li>
      ))}
    </Tag>
  );
  return [element, index];
}

/** An agent's words, formatted as they wrote them. */
export function Markdown({ text, className = "" }) {
  const blocks = blocksOf(text);
  const out = [];
  let index = 0;
  while (index < blocks.length) {
    const block = blocks[index];
    if (block.kind === "item") {
      let end = index;
      while (end < blocks.length && blocks[end].kind === "item") end += 1;
      const items = blocks.slice(index, end);
      const base = Math.min(...items.map((item) => item.depth));
      const normalised = items.map((item) => ({ ...item, depth: item.depth - base }));
      let at = 0;
      while (at < normalised.length) {
        const [element, next] = list(normalised, at, 0, `l${index}-${at}`);
        out.push(element);
        at = next;
      }
      index = end;
      continue;
    }
    if (block.kind === "code") out.push(<pre key={index} className="markdown__code">{block.text}</pre>);
    else if (block.kind === "heading") out.push(<p key={index} className="markdown__heading">{inline(block.text, `h${index}`)}</p>);
    else out.push(<p key={index}>{inline(block.text, `p${index}`)}</p>);
    index += 1;
  }
  return <div className={["markdown", className].filter(Boolean).join(" ")}>{out}</div>;
}

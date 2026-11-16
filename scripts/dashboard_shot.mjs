// A look at the running dashboard, for whoever cannot open a browser.
//
//   node scripts/dashboard_shot.mjs <url> <out.png> [--size=1440x900] [--scale=1] [--wait=3000] [step ...]
//
// Drives the installed Chrome (google-chrome on PATH) headless, over its
// debugging protocol, with nothing but Node (22 or later, for its WebSocket).
// Unlike `google-chrome --screenshot`, it does not wait for the page to go
// quiet, so pages that follow an event stream can be captured, and it can
// act on the page first. Steps run in order:
//
//   click:<name>           click the first button, link, tab or menu item with
//                          that accessible name or text (or starting with it)
//   hover:<name>           move the pointer over it
//   type:<label>=<value>   type into the field with that label
//   set:<label>=<value>    replace what the field holds
//   select:<label>=<text>  choose the option with that text
//   wait:<ms>
//
// `--text` also prints what the page says after the steps (the open dialog,
// or the page), which is how a control is checked without reading a picture.
// `--eval=<js>` prints what an expression gives in the page, for measuring.
// `--scale=3` magnifies, which is how alignment is checked. Use it against a
// copy of the database (`sqlite3 .foreman.db ".backup copy.db"`, then
// `foreman dashboard --port 8081 --db copy.db`) when a step would change
// something. See docs/TESTING.md, "Checking the look".
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2);
const [url, out] = args;
const opt = (name, fallback) => (args.find((a) => a.startsWith(`--${name}=`)) || `--${name}=${fallback}`).split("=")[1];
const [width, height] = opt("size", "1440x900").split("x").map(Number);
const scale = Number(opt("scale", "1"));
const wait = Number(opt("wait", "3000"));
const steps = args.slice(2).filter((a) => !a.startsWith("--"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn(
  "google-chrome",
  [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "shoot-"))}`,
    `--window-size=${width},${height}`, "about:blank",
  ],
  { stdio: "ignore" },
);

async function target() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(100);
  }
  throw new Error("Chrome did not start");
}

let nextId = 0;
const pending = new Map();
const ws = new WebSocket(await target());
await new Promise((r) => ws.addEventListener("open", r));
ws.addEventListener("message", (m) => {
  const data = JSON.parse(m.data);
  if (data.id && pending.has(data.id)) {
    pending.get(data.id)(data.result ?? data);
    pending.delete(data.id);
  }
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const id = (nextId += 1);
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });

const FIND = `(text) => {
  const layers = [...document.querySelectorAll('[role=dialog], [role=menu]')];
  const within = layers.length ? layers[layers.length - 1] : document;
  const all = [...within.querySelectorAll('button, a, [role=button], [role=menuitem], [role=tab], summary, label')];
  const name = (el) => (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\\s+/g, ' ');
  const el = all.find((e) => name(e) === text) || all.find((e) => name(e).startsWith(text));
  if (!el) return null;
  el.scrollIntoView({ block: 'center' });
  const r = el.getBoundingClientRect();
  return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
}`;

async function locate(text) {
  const { result } = await send("Runtime.evaluate", { expression: `(${FIND})(${JSON.stringify(text)})`, returnByValue: true });
  if (!result?.value) throw new Error(`Nothing named "${text}" on the page`);
  return result.value;
}

try {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: width < 500 });
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(wait);
  for (const step of steps) {
    const [kind, ...rest] = step.split(":");
    const value = rest.join(":");
    if (kind === "wait") await sleep(Number(value));
    else if (kind === "hover") {
      const p = await locate(value);
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: p.x, y: p.y });
      await sleep(300);
    } else if (kind === "click") {
      const p = await locate(value);
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: p.x, y: p.y });
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x: p.x, y: p.y, button: "left", clickCount: 1 });
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: p.x, y: p.y, button: "left", clickCount: 1 });
      await sleep(500);
    } else if (kind === "set" || kind === "select") {
      const [label, text] = value.split("=");
      const { result } = await send("Runtime.evaluate", {
        returnByValue: true,
        expression: `(() => {
          const l = [...document.querySelectorAll('label')].find((e) => e.textContent.trim().startsWith(${JSON.stringify(label)}));
          const f = (l && (document.getElementById(l.htmlFor) || l.querySelector('input, select, textarea')))
            || [...document.querySelectorAll('input, select, textarea')].find((e) => (e.getAttribute('aria-label') || '').startsWith(${JSON.stringify(label)}));
          if (!f) return 'no field';
          f.focus();
          if (f.tagName === 'SELECT') {
            const o = [...f.options].find((e) => e.textContent.trim() === ${JSON.stringify(text)} || e.value === ${JSON.stringify(text)});
            if (!o) return 'no option';
            const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
            set.call(f, o.value);
            f.dispatchEvent(new Event('change', { bubbles: true }));
            return 'ok';
          }
          f.select();
          return 'ok';
        })()`,
      });
      if (result?.value !== "ok") throw new Error(`${step}: ${result?.value}`);
      if (kind === "set") {
        await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
        await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
        if (text) await send("Input.insertText", { text });
      }
      await sleep(200);
    } else if (kind === "type") {
      const [label, text] = value.split("=");
      await send("Runtime.evaluate", {
        expression: `(() => { const l=[...document.querySelectorAll('label')].find((e)=>e.textContent.trim().startsWith(${JSON.stringify(label)})); const f=document.getElementById(l.htmlFor); f.focus(); })()`,
      });
      await send("Input.insertText", { text });
      await sleep(200);
    } else throw new Error(`Unknown step ${step}`);
  }
  const measure = args.find((a) => a.startsWith("--eval="));
  if (measure) {
    const { result } = await send("Runtime.evaluate", { returnByValue: true, expression: measure.slice("--eval=".length) });
    console.log(JSON.stringify(result?.value));
  }
  if (args.includes("--text")) {
    const { result } = await send("Runtime.evaluate", {
      returnByValue: true,
      expression: `(() => {
        const say = (el) => el.innerText.replace(/\\n{2,}/g, '\\n').trim();
        const dialog = document.querySelector('[role=dialog], [role=menu]');
        const notices = [...document.querySelectorAll('[role=alert], [role=status], .notice')].map(say).filter(Boolean);
        return (notices.length ? 'NOTICES: ' + notices.join(' | ') + '\\n' : '')
          + (dialog ? 'DIALOG: ' + say(dialog) : 'PAGE: ' + say(document.querySelector('main') || document.body)).slice(0, 1500);
      })()`,
    });
    console.log(result?.value ?? "");
  }
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  console.log(`wrote ${out}`);
} catch (error) {
  console.error(String(error.message || error));
  process.exitCode = 1;
} finally {
  ws.close();
  chrome.kill();
}

// The design rules ADR-0020 makes checkable: colours, sizes, radii and line
// weights live only in tokens.css, and pages do not fetch on their own.

const stylesheets = import.meta.glob("./*.css", { query: "?raw", import: "default", eager: true });
const sources = import.meta.glob(["../app/**/*.{js,jsx}", "../ui/**/*.{js,jsx}", "../pages/**/*.{js,jsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const HARD_CODED = [
  { name: "hex colour", pattern: /#[0-9a-fA-F]{3,8}\b/ },
  { name: "colour function", pattern: /\b(?:rgba?|hsla?)\(/ },
  { name: "pixel size", pattern: /\d(?:\.\d+)?px\b/ },
  { name: "rem or em size", pattern: /\d(?:\.\d+)?r?em\b/ },
];

function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

describe("design rules", () => {
  it("has a token stylesheet and stylesheets per area", () => {
    expect(Object.keys(stylesheets)).toEqual(expect.arrayContaining(["./tokens.css", "./base.css", "./shell.css", "./ui.css"]));
  });

  it("keeps colours, sizes and line weights in tokens.css", () => {
    const offences = [];
    for (const [file, css] of Object.entries(stylesheets)) {
      if (file === "./tokens.css") continue;
      stripComments(css)
        .split("\n")
        .forEach((line, index) => {
          // A media query cannot read a custom property; tokens.css records the breakpoint.
          if (line.trim().startsWith("@media")) return;
          for (const { name, pattern } of HARD_CODED) {
            if (pattern.test(line)) offences.push(`${file}:${index + 1} ${name}: ${line.trim()}`);
          }
        });
    }
    expect(offences).toEqual([]);
  });

  it("keeps inline styles out of components", () => {
    const offences = Object.entries(sources)
      .filter(([file]) => !/\.test\.jsx?$/.test(file))
      .filter(([, source]) => /\bstyle=\{/.test(source) || /#[0-9a-fA-F]{6}\b/.test(source))
      .map(([file]) => file);
    expect(offences).toEqual([]);
  });

  it("has pages load data through api/, never fetch directly", () => {
    const offences = Object.entries(sources)
      .filter(([file]) => file.startsWith("../pages/") || file.startsWith("../ui/"))
      .filter(([, source]) => /\bfetch\s*\(/.test(source))
      .map(([file]) => file);
    expect(offences).toEqual([]);
  });
});

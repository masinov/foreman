import { useLayoutEffect, useState } from "react";

/**
 * How many lines of a folded text fit beside the column next to it (owner,
 * 2026-11-23: the sprint's goal was cut at four lines however tall its
 * Details were).
 *
 * `mainRef` is the column holding the text; `asideRef` the column beside
 * it. The text is the first `.long-text__text` in the main column. While the
 * two sit side by side, the text may fill the aside's height, less room for
 * its "Show all"; never fewer than `least` lines. When they are stacked (a
 * narrow window) nothing is beside the text and the answer is null, so the
 * text keeps its own fold.
 */
export function useLinesBeside(mainRef, asideRef, { least = 4, deps = [] } = {}) {
  const [lines, setLines] = useState(null);

  useLayoutEffect(() => {
    const main = mainRef.current;
    const aside = asideRef.current;
    if (!main || !aside) return undefined;
    const fit = () => {
      const text = main.querySelector(".long-text__text");
      const lineHeight = text ? parseFloat(window.getComputedStyle(text).lineHeight) : NaN;
      const mainBox = main.getBoundingClientRect();
      const asideBox = aside.getBoundingClientRect();
      const besideEachOther = asideBox.height > 0 && Math.abs(asideBox.top - mainBox.top) < 1;
      if (!text || !Number.isFinite(lineHeight) || lineHeight <= 0 || !besideEachOther) {
        setLines(null);
        return;
      }
      const above = text.getBoundingClientRect().top - mainBox.top;
      // The "Show all" under a folded text takes about a line and a half.
      const room = asideBox.height - above - lineHeight * 1.5;
      setLines(Math.max(least, Math.floor(room / lineHeight)));
    };
    fit();
    window.addEventListener("resize", fit);
    const Observer = window.ResizeObserver;
    const observer = Observer ? new Observer(fit) : null;
    observer?.observe(aside);
    return () => {
      window.removeEventListener("resize", fit);
      observer?.disconnect();
    };
    // The caller names what changes the columns' content.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainRef, asideRef, least, ...deps]);

  return lines;
}

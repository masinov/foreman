import React from "react";

import { formatMoney, formatTokens } from "./format";
import { Mono } from "./Mono";

/**
 * The one way spend is written (design README, Words): the amount first, the
 * tokens after it ("$0.09 · 3.5K tokens"), all in the mono number font.
 * A zero is blank in a table column or a list row (`where="row"`) and
 * "$0.00" in a details row or a heading (`where="details"`, the default).
 * Tokens alone are written without an amount. Nothing to say gives nothing.
 */
export function spendWords(amount, tokens = 0, where = "details") {
  const money = Number(amount) || 0;
  const count = Number(tokens) || 0;
  const parts = [];
  if (money || (where === "details" && !count)) parts.push(formatMoney(money));
  if (count) parts.push(`${formatTokens(count)} tokens`);
  return where === "row" && !money && !count ? "" : parts.join(" · ");
}

export function Spend({ amount, tokens = 0, where = "details", quiet = false, className = "" }) {
  const words = spendWords(amount, tokens, where);
  if (!words) return null;
  return (
    <Mono quiet={quiet} className={className}>
      {words}
    </Mono>
  );
}

/** Titan brand mark — angular glyph for approved branding locations only.
 * Never replaces functional status dots. Never used as a decorative sphere.
 */

import { div } from "./dom-utils.js";

/** Inline SVG mark (no external fetch — works under static /app mount). */
const TITAN_LOGO_SVG = `
<svg class="tdl-v2-brand-mark__svg" viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
  <path d="M16 2.5 L27.5 9.2 V18.4 L16 29.5 L4.5 18.4 V9.2 Z"
    stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"
    fill="rgba(225,29,46,0.12)"/>
  <path d="M16 6.2 L23.4 10.6 V16.8 L16 24.2 L8.6 16.8 V10.6 Z"
    stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"
    fill="rgba(255,77,90,0.18)"/>
  <path d="M16 10.4 L19.8 12.8 V16.4 L16 19.8 L12.2 16.4 V12.8 Z"
    fill="#FFEAEC" opacity="0.92"/>
  <path d="M11.2 11.8 L16 8.8 L20.8 11.8"
    stroke="#FFFFFF" stroke-width="1.05" stroke-linecap="round"
    stroke-linejoin="round" opacity="0.85"/>
</svg>
`.trim();

/**
 * @param {{
 *   className?: string,
 *   size?: "sm"|"md"|"lg",
 *   decorative?: boolean,
 *   label?: string,
 * }} [options]
 * @returns {HTMLElement}
 */
export function createTitanLogo(options = {}) {
  const size = options.size || "md";
  const mark = div(
    `tdl-v2-brand-mark tdl-v2-brand-mark--${size}${
      options.className ? ` ${options.className}` : ""
    }`,
  );
  mark.dataset.brand = "titan-logo";
  if (options.decorative !== false) {
    mark.setAttribute("aria-hidden", "true");
  } else {
    mark.setAttribute("role", "img");
    mark.setAttribute("aria-label", options.label || "Titan AI");
  }
  mark.innerHTML = TITAN_LOGO_SVG;
  return mark;
}

/**
 * Compact brand mark suitable for button glyphs (sidebar toggle).
 * @returns {HTMLElement}
 */
export function createTitanLogoGlyph() {
  const glyph = createTitanLogo({ size: "sm", className: "tdl-v2-sidebar-toggle__logo" });
  glyph.classList.add("tdl-v2-sidebar-toggle__glyph");
  return glyph;
}

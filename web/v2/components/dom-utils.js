/** Titan Frontend V2 — DOM construction helpers. */

/**
 * @param {string} tag
 * @param {string} [className]
 * @param {Record<string, string>} [attrs]
 * @returns {HTMLElement}
 */
export function el(tag, className = "", attrs = {}) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") {
      node.textContent = value;
    } else if (key === "html") {
      node.innerHTML = value;
    } else {
      node.setAttribute(key, value);
    }
  }
  return node;
}

/**
 * @param {string} className
 * @param {Record<string, string>} [attrs]
 * @returns {HTMLDivElement}
 */
export function div(className = "", attrs = {}) {
  return /** @type {HTMLDivElement} */ (el("div", className, attrs));
}

/**
 * @param {string} viewBox
 * @param {string} inner
 * @param {number} [size]
 * @returns {SVGElement}
 */
export function svgIcon(viewBox, inner, size = 16) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("fill", "none");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = inner;
  return svg;
}

/** @param {HTMLElement} parent @param {...(HTMLElement | string | null | undefined)[]} children */
export function appendChildren(parent, ...children) {
  for (const child of children) {
    if (child == null) {
      continue;
    }
    if (typeof child === "string") {
      parent.appendChild(document.createTextNode(child));
    } else {
      parent.appendChild(child);
    }
  }
}

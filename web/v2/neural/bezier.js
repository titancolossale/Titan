/** Titan Neural Renderer V3 — Cubic Bezier path utilities for organic axons. */

/** @param {number} t @param {number} p0 @param {number} p1 @param {number} p2 @param {number} p3 */
export function cubicAt(t, p0, p1, p2, p3) {
  const u = 1 - t;
  return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
}

/**
 * Sample point on cubic Bezier edge.
 * @param {object} edge
 * @param {object} na
 * @param {object} nb
 * @param {number} t
 */
export function sampleEdge(edge, na, nb, t) {
  const x0 = na.x;
  const y0 = na.y;
  const x3 = nb.x;
  const y3 = nb.y;
  const x1 = edge.cp1x ?? (x0 + x3) * 0.5;
  const y1 = edge.cp1y ?? (y0 + y3) * 0.5;
  const x2 = edge.cp2x ?? (x0 + x3) * 0.5;
  const y2 = edge.cp2y ?? (y0 + y3) * 0.5;
  return {
    x: cubicAt(t, x0, x1, x2, x3),
    y: cubicAt(t, y0, y1, y2, y3),
  };
}

/**
 * Build organic control points for an axon/dendrite connection.
 *
 * Short synapses curve like biology. Tangle mode allows richer bend inside the
 * core organism. Field axons stay local — never long geometric rulers.
 *
 * @param {object} na
 * @param {object} nb
 * @param {number} [curveStrength]
 * @param {number} [seed]
 * @param {{ radial?: boolean, maxBendRatio?: number, tangle?: boolean }} [opts]
 */
export function buildOrganicControls(na, nb, curveStrength = 0.35, seed = Math.random(), opts = {}) {
  const dx = nb.x - na.x;
  const dy = nb.y - na.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const nx = -dy / dist;
  const ny = dx / dist;

  const tangle = Boolean(opts.tangle);
  const defaultMax = tangle ? 0.62 : opts.radial ? 0.28 : 0.48;
  const maxRatio = opts.maxBendRatio ?? defaultMax;
  const strength = Math.max(0.08, Math.min(1.35, curveStrength));
  const bendMag = dist * Math.min(maxRatio, strength * (tangle ? 0.58 : 0.48)) * (0.55 + seed * 0.5);
  const sign = seed > 0.5 ? 1 : -1;
  const bend = bendMag * sign;
  const asym = tangle ? 0.18 + seed * 0.55 : 0.24 + seed * 0.42;
  // Slight along-path jitter so curves never read as uniform geometry.
  const jitter = tangle ? dist * 0.08 * (seed - 0.5) : dist * 0.03 * (seed - 0.5);

  return {
    cp1x: na.x + dx * asym + nx * bend * 0.75 + nx * jitter,
    cp1y: na.y + dy * asym + ny * bend * 0.75 + ny * jitter,
    cp2x: na.x + dx * (1 - asym) + nx * bend * 1.05 - nx * jitter * 0.6,
    cp2y: na.y + dy * (1 - asym) + ny * bend * 1.05 - ny * jitter * 0.6,
  };
}

/**
 * Trace a multi-point organic strand as chained quadratic curves.
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<{ x: number, y: number }>} pts screen-space points
 * @param {number} [phase] subtle living offset
 */
export function traceStrand(ctx, pts, phase = 0) {
  if (!pts || pts.length < 2) return;
  const wobble = Math.sin(phase) * 0.6;
  ctx.moveTo(pts[0].x, pts[0].y);
  if (pts.length === 2) {
    ctx.lineTo(pts[1].x + wobble * 0.3, pts[1].y);
    return;
  }
  for (let i = 1; i < pts.length - 1; i++) {
    const curr = pts[i];
    const next = pts[i + 1];
    const mx = (curr.x + next.x) * 0.5;
    const my = (curr.y + next.y) * 0.5;
    const ox = Math.sin(phase + i * 0.7) * wobble;
    const oy = Math.cos(phase + i * 0.55) * wobble;
    ctx.quadraticCurveTo(curr.x + ox, curr.y + oy, mx + ox * 0.4, my + oy * 0.4);
  }
  const last = pts[pts.length - 1];
  ctx.lineTo(last.x, last.y);
}

/**
 * Trace a cubic Bezier axon into the canvas path.
 *
 * IMPORTANT: endpoints and control points must live in the SAME coordinate
 * space. Edge control points are stored in WORLD space, so the caller must
 * project them to screen space (see `NeuralRenderer._screenXY`) and pass them
 * here. Mixing world-space controls with screen-space endpoints produced the
 * full-screen diagonal "warp" streaks this renderer used to show.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{ x: number, y: number }} pa screen-space start
 * @param {{ x: number, y: number }} pb screen-space end
 * @param {{ x: number, y: number } | null} [c1] screen-space control near pa
 * @param {{ x: number, y: number } | null} [c2] screen-space control near pb
 */
export function traceEdge(ctx, pa, pb, c1 = null, c2 = null) {
  ctx.moveTo(pa.x, pa.y);
  if (c1 && c2) {
    ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, pb.x, pb.y);
  } else {
    ctx.lineTo(pb.x, pb.y);
  }
}

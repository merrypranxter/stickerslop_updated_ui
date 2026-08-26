#!/usr/bin/env node
/**
 * Phase 0 — compositing pipeline unification for Sticker Slop Studio.
 *
 * RUN FROM THE REPO ROOT:  node apply_phase0_pipeline.cjs
 * It rewrites index.html in place:
 *   1. Extracts a shared compositeLayerEffects(off, l, time, ctx, opts) from
 *      renderMediaLayer (adjustments -> applyLayerMask -> erase-mask hook ->
 *      glitter -> glitch -> composite).
 *   2. renderMediaLayer keeps source selection + bgRemove + chroma key,
 *      then delegates to the shared pipeline.
 *   3. renderTextLayer draws onto its own offscreen canvas first, then runs
 *      the same pipeline — masking / adjustments / erase now work on text.
 *
 * The script is idempotent-unsafe by design: run it exactly once against a
 * pristine index.html. It asserts every anchor before touching the file and
 * aborts without writing if anything is unexpected.
 */
const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'index.html');
let src = fs.readFileSync(FILE, 'utf8');

function mustFind(s, anchor) {
  const first = s.indexOf(anchor);
  const last = s.lastIndexOf(anchor);
  if (first === -1 || first !== last) {
    throw new Error('anchor not unique or missing: ' + JSON.stringify(anchor.slice(0, 80)));
  }
  return first;
}

function between(s, startAnchor, endAnchor, inclEnd) {
  const i = mustFind(s, startAnchor);
  const j = s.indexOf(endAnchor, i + startAnchor.length);
  if (j === -1) throw new Error('end anchor missing after: ' + JSON.stringify(startAnchor.slice(0, 60)));
  return { text: s.slice(i, inclEnd ? j + endAnchor.length : j), i, end: inclEnd ? j + endAnchor.length : j };
}

// ============================================================
// STEP 1: extract segments from current renderMediaLayer
// ============================================================

const mediaHead = between(src,
  'function renderMediaLayer(ctx, l, time) {',
  'octx.drawImage(imgSource, 0, 0, w, h);',
  true);

const chromaInner = between(src,
  '    let ckColors = Array.isArray(l.chroma.colors) ? l.chroma.colors : null;',
  '\n  }\n  \n  // Tone Curves & LUTs Preparation',
  false);

const segAdj = between(src,
  '  // Tone Curves & LUTs Preparation',
  '  octx.putImageData(imgData, 0, 0);',
  true);

const tailEndAnchor = '  } else {\n    ctx.save();\n    ctx.drawImage(off, -w/2, -h/2);\n    ctx.restore();\n  }';
const segTail = between(src,
  '  // Apply Masking & Shape Cutout System',
  tailEndAnchor,
  true);

if (!(mediaHead.i < chromaInner.i && chromaInner.i < segAdj.i && segAdj.i < segTail.i)) {
  throw new Error('segment order wrong');
}
if (segTail.end - mediaHead.i > 20000) {
  throw new Error('renderMediaLayer extraction span suspiciously large');
}

// ============================================================
// STEP 2: build compositeLayerEffects from extracted segments
// ============================================================

let segTailMod = segTail.text;

const oldGlitter = '  if (l.glitter && l.glitter.en) {';
if (segTailMod.split(oldGlitter).length !== 2) throw new Error('glitter anchor not unique in tail');
segTailMod = segTailMod.replace(oldGlitter,
  '  if (!opts.skipGlitter && l.glitter && l.glitter.en) {');

const oldGlitch = "  const hasMediaGlitch = (l.glitch && l.glitch.en) || (Array.isArray(l.anims) && l.anims.some(a => a.type === 'glitch'));";
if (segTailMod.split(oldGlitch).length !== 2) throw new Error('glitch anchor not unique in tail');
segTailMod = segTailMod.replace(oldGlitch,
  "  const hasMediaGlitch = !opts.skipGlitch && ((l.glitch && l.glitch.en) || (Array.isArray(l.anims) && l.anims.some(a => a.type === 'glitch')));");

const oldMask = '  if (l.mask && l.mask.en) {\n    applyLayerMask(off, l);\n  }';
if (segTailMod.split(oldMask).length !== 2) throw new Error('mask anchor not unique in tail');
segTailMod = segTailMod.replace(oldMask,
`  if (l.mask && l.mask.en) {
    applyLayerMask(off, l);
  }

  // Erase-mask hook (Phase 2): persistent hand-painted eraser canvas,
  // applied non-destructively after the mask, before the final composite.
  if (l.eraseMask) {
    octx.save();
    octx.globalCompositeOperation = 'destination-out';
    octx.drawImage(l.eraseMask, 0, 0, w, h);
    octx.restore();
  }`);

const compositeFn = `// --------------------------------------------------------
// UNIFIED COMPOSITING PIPELINE (PHASE 0)
// Shared by media, text and sparkle layers:
//   adjustments -> applyLayerMask -> erase-mask -> glitter/glitch -> composite
// \`off\` is the layer's own offscreen canvas (content already drawn, centered).
// \`ctx\` is the main render context (already translated/rotated/scaled so the
// layer is centered on the origin). opts.skipGlitter / opts.skipGlitch let a
// renderer opt out when it already handled that effect internally (text does).
// --------------------------------------------------------
function compositeLayerEffects(off, l, time, ctx, opts) {
  opts = opts || {};
  const w = off.width;
  const h = off.height;
  if (w <= 0 || h <= 0) return;
  const octx = off.getContext('2d', { willReadFrequently: true });
  // Renderers may leave a transform on the layer canvas context (text centers
  // its coordinate system). Mask/erase ops must run in raw device pixels.
  octx.setTransform(1, 0, 0, 1, 0, 0);
  let imgData = octx.getImageData(0, 0, w, h);
  let d = imgData.data;

${segAdj.text}

${segTailMod}
}
window.compositeLayerEffects = compositeLayerEffects;`;

// ============================================================
// STEP 3: build the new, slim renderMediaLayer
// ============================================================

const newMediaFn = `${mediaHead.text}

  // Chroma Key (multi-color: alpha is cleared if ANY key color matches)
  if (l.chroma && l.chroma.en) {
    const imgData = octx.getImageData(0, 0, w, h);
    const d = imgData.data;
${chromaInner.text}
    octx.putImageData(imgData, 0, 0);
  }

  // Unified compositing pipeline (Phase 0): adjustments -> mask -> erase -> glitter/glitch
  compositeLayerEffects(off, l, time, ctx);
}`;

// ============================================================
// STEP 4: replace the whole old renderMediaLayer region
// ============================================================
const regionStart = mustFind(src, 'function renderMediaLayer(ctx, l, time) {');
const regionEndAnchor = '\n// --------------------------------------------------------\n// LAYER STACK OPERATIONS';
const regionEnd = src.indexOf(regionEndAnchor, regionStart);
if (regionEnd === -1) throw new Error('LAYER STACK header not found after renderMediaLayer');
const oldRegion = src.slice(regionStart, regionEnd);
if (oldRegion.split('function ').length - 1 !== 1) throw new Error('region contains unexpected functions');

const newRegion = compositeFn + '\n\n' + newMediaFn + '\n';
src = src.slice(0, regionStart) + newRegion + src.slice(regionEnd);

// ============================================================
// STEP 5: renderTextLayer — offscreen canvas setup
// ============================================================
const tAnchor = '  if (maxWidth < 20) maxWidth = 20;\n  if (totalHeight < 20) totalHeight = 20;\n';
if (src.split(tAnchor).length !== 2) throw new Error('text measurement anchor not unique');
const tInsert = tAnchor + `
  // PHASE 0: render text onto its own offscreen canvas so the unified
  // compositing pipeline (adjustments / mask / erase) applies to text too.
  // Pad for strokes, shadow, extrude, plate and per-letter motion overflow.
  const __targetCtx = ctx;
  const __strokePad = (parseInt(l.s1w) || 0) / 2 + (parseInt(l.s2w) || 0) + (parseInt(l.s3w) || 0);
  const __shadowPad = (l.shb > 0) ? ((l.shb || 0) + Math.max(Math.abs(l.shx || 0), Math.abs(l.shy || 0))) : 0;
  const __extrudePad = (l.extrude && l.extrude.en) ? (Math.max(Math.abs(l.extrude.x || 0), Math.abs(l.extrude.y || 0)) * (l.extrude.d || 10)) : 0;
  const __platePad = (l.plate && l.plate.en) ? (l.plate.pad || 0) : 0;
  const __motionPad = (l.motion && l.motion.type && l.motion.type !== 'none') ? (parseFloat(l.motion.amt) || 20) : 0;
  const __pad = Math.ceil(__strokePad + __shadowPad + __extrudePad + __platePad + __motionPad) + 56;
  const __offW = Math.min(4096, Math.ceil(maxWidth + __pad * 2));
  const __offH = Math.min(4096, Math.ceil(totalHeight + __pad * 2));
  const off = document.createElement('canvas');
  off.width = __offW; off.height = __offH;
  ctx = off.getContext('2d', { willReadFrequently: true });
  ctx.translate(__offW / 2, __offH / 2);
`;
src = src.replace(tAnchor, tInsert);

// ============================================================
// STEP 6: fast glitter path — composite through the pipeline
// ============================================================
const fastAnchor = '      ctx.save();\n      ctx.drawImage(activeGlitterFrame, -activeGlitterFrame.width / 2, -activeGlitterFrame.height / 2);\n      ctx.restore();\n      return;';
if (src.split(fastAnchor).length !== 2) throw new Error('fast glitter anchor not unique');
const fastNew = '      ctx.save();\n      ctx.drawImage(activeGlitterFrame, -activeGlitterFrame.width / 2, -activeGlitterFrame.height / 2);\n      ctx.restore();\n      compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: true });\n      return;';
src = src.replace(fastAnchor, fastNew);

// ============================================================
// STEP 7: text glitch — layer opacity is applied at composite time now
// ============================================================
const baseopAnchor = "    const sliceJitter = Math.sin(time * 25 + 9) > 0.4 ? (Math.cos(time * 40) * dist * 1.5) : 0;\n    const baseOp = (typeof l.opacity === 'number' && !isNaN(l.opacity)) ? Math.max(0, Math.min(1, l.opacity)) : 1;";
if (src.split(baseopAnchor).length !== 2) throw new Error('text glitch baseOp anchor not unique');
const baseopNew = "    const sliceJitter = Math.sin(time * 25 + 9) > 0.4 ? (Math.cos(time * 40) * dist * 1.5) : 0;\n    // Phase 0: text renders offscreen; layer opacity is applied once by the\n    // main ctx when the finished canvas is composited — keep RGB passes relative.\n    const baseOp = 1;";
src = src.replace(baseopAnchor, baseopNew);

// ============================================================
// STEP 8: renderTextLayer tail — run the pipeline, composite to main ctx
// ============================================================
const tailAnchor = '  } else {\n    drawPass(null, 0, 0);\n  }\n}';
if (src.split(tailAnchor).length !== 2) throw new Error('text tail anchor not unique');
const tailNew = `  } else {
    drawPass(null, 0, 0);
  }

  // PHASE 0: adjustments -> mask -> erase, then composite the finished text
  // canvas onto the main ctx (glitter/glitch already handled above for text).
  compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: hasGlitchAnim });
}`;
src = src.replace(tailAnchor, tailNew);

// ============================================================
fs.writeFileSync(FILE, src, 'utf8');
console.log('OK — Phase 0 patch applied, ' + src.length + ' chars written to index.html');

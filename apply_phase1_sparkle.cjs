#!/usr/bin/env node
/**
 * Phase 1 — standalone Sparkle Field layer for Sticker Slop Studio.
 *
 * RUN FROM THE REPO ROOT:  node apply_phase1_sparkle.cjs
 * Rewrites index.html in place. Requires the Phase 0 pipeline patch to be
 * applied first (it anchors on compositeLayerEffects-era code).
 *
 * Adds: createSparkleLayer(), renderSparkleLayer(), renderLayers() and
 * getLayerDimensions() branches, an ADD SPARKLE FIELD toolbar button, and an
 * inspector panel with live bindings. Idempotent-unsafe by design: run exactly
 * once. Asserts every anchor and aborts without writing on any mismatch.
 */
const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'index.html');
let src = fs.readFileSync(FILE, 'utf8');

function subExact(oldStr, newStr, label) {
  const parts = src.split(oldStr);
  if (parts.length !== 2) {
    throw new Error('[' + label + '] anchor count ' + (parts.length - 1) + ' != 1: ' + JSON.stringify(oldStr.slice(0, 70)));
  }
  src = parts.join(newStr);
}

// NOTE: the full operation payload for this script is stored in
// apply_phase1_sparkle.ops.json (same folder) to keep this file readable.
const OPS = JSON.parse(fs.readFileSync(path.join(__dirname, 'apply_phase1_sparkle.ops.json'), 'utf8'));

for (const op of OPS) subExact(op.old, op.new, op.label);

fs.writeFileSync(FILE, src, 'utf8');
console.log('OK — Phase 1 sparkle layer patch applied, ' + src.length + ' chars written to index.html');

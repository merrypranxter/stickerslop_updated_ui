#!/usr/bin/env node
/**
 * apply_phase05_fixes.cjs — Sticker Slop Studio "Build Brief R1" Phase 0.5
 *
 * Scripted string-replace patch for index.html (same pattern as
 * apply_full_glitter_integration.cjs). Every anchor is asserted to occur
 * exactly once before replacement, so the script fails loudly instead of
 * silently no-op'ing if the file has drifted.
 *
 * Usage:  node apply_phase05_fixes.cjs
 *
 * Contains:
 *   1. Locked layers are no longer selectable on canvas click (click-through,
 *      toast kept, no selection change)
 *   2. "Lock proportions" checkbox now gates the Stretch X/Y sliders
 *   3. Multi-color chroma key (colors array + per-color tolerance, chip UI,
 *      legacy single-color migration)
 *   4. Remove-background is now a live, non-destructive per-layer effect
 *      with a tolerance slider (source assets are never mutated)
 *   5. Bottom sheet is resizable by dragging the .sheet-grab handle
 */

const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, 'index.html');
let s = fs.readFileSync(FILE, 'utf8');

function subExact(oldStr, newStr) {
  const count = s.split(oldStr).length - 1;
  if (count !== 1) {
    console.error(`FATAL: anchor found ${count}x (expected 1):\n${oldStr.slice(0, 120)}`);
    process.exit(1);
  }
  s = s.replace(oldStr, newStr);
}

function subRegex(re, newStr) {
  const matches = s.match(new RegExp(re.source, 'gs'));
  if (!matches || matches.length !== 1) {
    console.error(`FATAL: regex matched ${matches ? matches.length : 0}x (expected 1): ${re.source.slice(0, 120)}`);
    process.exit(1);
  }
  s = s.replace(re, newStr);
}

// ------------------------------------------------------------------
// 1. Locked layers: inert to clicks (no selection change), toast kept
// ------------------------------------------------------------------
subExact(
`      if (Math.abs(lx) <= sw / 2 + 16 && Math.abs(ly) <= sh / 2 + 16) {
        appState.selectedId = l.id;
        appState.selectedIds = new Set([l.id]);
        updateUI();
        if (typeof showToast === 'function') {
          showToast(\`🔒 "\${l.name || 'Layer'}" is locked. Click "Unlock" in the toolbar to move or scale it.\`, 3000);
        }
        return;
      }`,
`      if (Math.abs(lx) <= sw / 2 + 16 && Math.abs(ly) <= sh / 2 + 16) {
        // Locked layers are inert to clicks/taps: no selection change.
        // Fall through so the tap behaves like an empty-canvas click
        // (click-through); keep the toast purely as a hint.
        if (typeof showToast === 'function') {
          showToast(\`🔒 "\${l.name || 'Layer'}" is locked. Click "Unlock" in the toolbar to move or scale it.\`, 3000);
        }
        break;
      }`);

// ------------------------------------------------------------------
// 2. Stretch X slider honors "Lock proportions"
// ------------------------------------------------------------------
subExact(
`  scaleXSlider.oninput = e => {
    const l = appState.layers.find(x => x.id === appState.selectedId);
    if (!l || l.locked) return;
    const signX = (l.scaleX < 0) ? -1 : 1;
    l.scaleX = signX * sliderToScale(e.target.value);
    renderProperties();
    renderFrame(appState.time);
  };`,
`  scaleXSlider.oninput = e => {
    const l = appState.layers.find(x => x.id === appState.selectedId);
    if (!l || l.locked) return;
    const signX = (l.scaleX < 0) ? -1 : 1;
    const newScaleX = sliderToScale(e.target.value);
    const lockAspect = document.getElementById('prop-scale-lock-aspect')?.checked ?? true;
    if (lockAspect) {
      // Locked: recompute Y from X to preserve the layer's current ratio
      const ratio = Math.abs((l.scaleY !== undefined ? l.scaleY : 1) / (l.scaleX || 1));
      const signY = (l.scaleY < 0) ? -1 : 1;
      l.scaleX = signX * newScaleX;
      l.scaleY = signY * newScaleX * ratio;
    } else {
      l.scaleX = signX * newScaleX;
    }
    renderProperties();
    renderFrame(appState.time);
  };`);

// ------------------------------------------------------------------
// 3. Stretch Y slider honors "Lock proportions"
// ------------------------------------------------------------------
subExact(
`  scaleYSlider.oninput = e => {
    const l = appState.layers.find(x => x.id === appState.selectedId);
    if (!l || l.locked) return;
    const signY = (l.scaleY < 0) ? -1 : 1;
    l.scaleY = signY * sliderToScale(e.target.value);
    renderProperties();
    renderFrame(appState.time);
  };`,
`  scaleYSlider.oninput = e => {
    const l = appState.layers.find(x => x.id === appState.selectedId);
    if (!l || l.locked) return;
    const signY = (l.scaleY < 0) ? -1 : 1;
    const newScaleY = sliderToScale(e.target.value);
    const lockAspect = document.getElementById('prop-scale-lock-aspect')?.checked ?? true;
    if (lockAspect) {
      // Locked: recompute X from Y to preserve the layer's current ratio
      const ratio = Math.abs((l.scaleX !== undefined ? l.scaleX : 1) / (l.scaleY || 1));
      const signX = (l.scaleX < 0) ? -1 : 1;
      l.scaleY = signY * newScaleY;
      l.scaleX = signX * newScaleY * ratio;
    } else {
      l.scaleY = signY * newScaleY;
    }
    renderProperties();
    renderFrame(appState.time);
  };`);

// ------------------------------------------------------------------
// 4. Multi-color chroma key render loop (legacy single-color fallback kept)
// ------------------------------------------------------------------
subRegex(
  /  \/\/ Chroma Key\n  if \(l\.chroma && l\.chroma\.en\) \{\n[\s\S]*?\n  \}\n/,
`  // Chroma Key (multi-color: alpha is cleared if ANY key color matches)
  if (l.chroma && l.chroma.en) {
    let ckColors = Array.isArray(l.chroma.colors) ? l.chroma.colors : null;
    if (!ckColors) {
      // Backward compat: legacy single-color shape { c, t }
      ckColors = [{ c: l.chroma.c || '#00ff00', t: l.chroma.t !== undefined ? l.chroma.t : 0.1 }];
    }
    const ckParsed = ckColors.map(k => ({
      r: parseInt((k.c || '#00ff00').substr(1, 2), 16),
      g: parseInt((k.c || '#00ff00').substr(3, 2), 16),
      b: parseInt((k.c || '#00ff00').substr(5, 2), 16),
      tol: (k.t !== undefined ? k.t : 0.1) * 441.67
    }));
    for (let i = 0; i < d.length; i += 4) {
      if (d[i+3] === 0) continue;
      for (let k = 0; k < ckParsed.length; k++) {
        const kp = ckParsed[k];
        const dist = Math.sqrt((d[i]-kp.r)**2 + (d[i+1]-kp.g)**2 + (d[i+2]-kp.b)**2);
        if (dist < kp.tol) { d[i+3] = 0; break; }
      }
    }
  }
`);

// ------------------------------------------------------------------
// 5. Chroma UI markup: chip list + add button
// ------------------------------------------------------------------
subExact(
`            <div class="prop-row"><label>Enable</label><input type="checkbox" id="media-ck-en"></div>
            <div class="prop-row"><label>Color</label><input type="color" id="media-ck-c"></div>
            <div class="prop-row"><label>Tolerance</label><input type="range" min="0" max="1" step="0.01" id="media-ck-t"></div>`,
`            <div class="prop-row"><label>Enable</label><input type="checkbox" id="media-ck-en"></div>
            <div class="prop-row" style="align-items:flex-start;"><label>Key Colors</label><div id="media-ck-colors" style="flex:1; display:flex; flex-direction:column; gap:6px;"></div></div>
            <button type="button" id="media-ck-add" class="win-btn" style="width:100%; padding:4px; font-size:10.5px; font-weight:800; cursor:pointer;">+ Add Key Color</button>`);

// ------------------------------------------------------------------
// 6. Chroma binding in renderProperties: migrate shape + render chip editor
// ------------------------------------------------------------------
subExact(
`    bind('media-ck-en', l.chroma, 'en'); bind('media-ck-c', l.chroma, 'c', true); bind('media-ck-t', l.chroma, 't');`,
`    if (!Array.isArray(l.chroma.colors)) { l.chroma = { en: !!l.chroma.en, colors: [{ c: l.chroma.c || '#00ff00', t: l.chroma.t !== undefined ? l.chroma.t : 0.1 }] }; }
    bind('media-ck-en', l.chroma, 'en');
    renderChromaKeyEditor(l);`);

// ------------------------------------------------------------------
// 7. createMediaLayer: new chroma shape + bgRemove defaults
// ------------------------------------------------------------------
subExact(
`    chroma: { en: false, c: '#00ff00', t: 0.1 },`,
`    chroma: { en: false, colors: [{ c: '#00ff00', t: 0.1 }] },
    bgRemove: { en: false, tolerance: 36 },`);

// ------------------------------------------------------------------
// 8. Media reset button: new chroma shape + bgRemove reset
// ------------------------------------------------------------------
subExact(
`    l.chroma = { en: false, c: '#00ff00', t: 0.1 };`,
`    l.chroma = { en: false, colors: [{ c: '#00ff00', t: 0.1 }] };
    l.bgRemove = { en: false, tolerance: 36 };`);

// ------------------------------------------------------------------
// 9. Remove-background UI: live toggle + tolerance slider
// ------------------------------------------------------------------
subExact(
`            <div style="font-size:10px; color:#999; margin-bottom: 5px; line-height:1.3;">Auto edge & flood-fill transparent background keying. Works on images & animated GIFs.</div>
            <button id="btn-remove-bg" class="win-btn" style="width:100%; padding:6px; font-weight:bold; cursor:pointer;">⚡ Remove Background</button>`,
`            <div style="font-size:10px; color:#999; margin-bottom: 5px; line-height:1.3;">Auto edge & flood-fill transparent background keying. Works on images & animated GIFs. Non-destructive: toggle on, then tune tolerance live.</div>
            <div class="prop-row"><label>Enable (Live)</label><input type="checkbox" id="media-bgrm-en"></div>
            <div class="prop-row"><label>Tolerance</label><input type="range" min="0" max="150" step="1" id="media-bgrm-t"></div>
            <button id="btn-remove-bg" class="win-btn" style="width:100%; padding:6px; font-weight:bold; cursor:pointer;">⚡ Remove Background (One-Tap)</button>`);

// ------------------------------------------------------------------
// 10. bgRemove binding in renderProperties
// ------------------------------------------------------------------
subExact(
`    const btnRemoveBg = document.getElementById('btn-remove-bg');
    if (btnRemoveBg) btnRemoveBg.onclick = doRemoveBackground;`,
`    const btnRemoveBg = document.getElementById('btn-remove-bg');
    if (btnRemoveBg) btnRemoveBg.onclick = doRemoveBackground;
    if (!l.bgRemove) l.bgRemove = { en: false, tolerance: 36 };
    bind('media-bgrm-en', l.bgRemove, 'en'); bind('media-bgrm-t', l.bgRemove, 'tolerance');`);

// ------------------------------------------------------------------
// 11. renderMediaLayer: apply live bg removal to the source (cached)
// ------------------------------------------------------------------
subRegex(
  /  if \(!imgSource\) return;\n[ \t]*\n  const w = asset\.width \|\| 200;/,
`  if (!imgSource) return;

  // Live, non-destructive background removal (images / GIF frame canvases only;
  // the source asset is never mutated — result is cached per source+tolerance)
  if (l.bgRemove && l.bgRemove.en && asset.type !== 'video') {
    imgSource = getBgRemovedSource(imgSource, l.bgRemove.tolerance !== undefined ? l.bgRemove.tolerance : 36);
  }

  const w = asset.width || 200;`);

// ------------------------------------------------------------------
// 12. doRemoveBackground: non-destructive one-tap enable
// ------------------------------------------------------------------
subRegex(
  /async function doRemoveBackground\(\) \{[\s\S]*?\n\}\n/,
`async function doRemoveBackground() {
  // Non-destructive: enable the live per-layer effect instead of
  // permanently overwriting the asset's pixels.
  const l = appState.layers.find(x => x.id === appState.selectedId);
  if (!l || l.type !== 'media') return;

  const status = document.getElementById('bg-remove-status');
  if (!l.bgRemove) l.bgRemove = { en: false, tolerance: 36 };
  pushUndoState('Remove Background (Live)');
  l.bgRemove.en = true;

  if (l.glitter) {
    glitterFrameCache.delete(l.id);
  }

  if (status) {
    status.style.display = 'block';
    status.innerText = '\\u2705 Live background removal enabled — tune the Tolerance slider to taste.';
    setTimeout(() => { if (status) status.style.display = 'none'; }, 2500);
  }
  renderProperties();
  renderFrame(appState.time);
}
`);

// ------------------------------------------------------------------
// 13. Helpers: bg-remove source cache + chroma chip editor
// ------------------------------------------------------------------
subExact(
`function smartRemoveCanvasBackground(srcCanvas, options = {}) {`,
`// Live, non-destructive background removal cache.
// Keyed by the SOURCE canvas (still image canvas / individual GIF frame), so
// re-renders at the same tolerance are free and original assets stay intact.
const bgRemoveSrcCache = new WeakMap();
function getBgRemovedSource(src, tolerance) {
  if (!src) return src;
  const w = src.width || src.naturalWidth || 0;
  const h = src.height || src.naturalHeight || 0;
  if (!w || !h) return src;
  const entry = bgRemoveSrcCache.get(src);
  if (entry && entry.tolerance === tolerance) return entry.result;
  let srcCanvas = src;
  if (!(src instanceof HTMLCanvasElement)) {
    // Still images arrive as HTMLImageElement — rasterize once (cached below)
    srcCanvas = document.createElement('canvas');
    srcCanvas.width = w; srcCanvas.height = h;
    srcCanvas.getContext('2d', { willReadFrequently: true }).drawImage(src, 0, 0, w, h);
  }
  const result = smartRemoveCanvasBackground(srcCanvas, { tolerance });
  bgRemoveSrcCache.set(src, { tolerance, result });
  return result;
}

// Multi-color chroma key editor: one chip per key color, each with its own
// tolerance slider and remove button, plus an "+ Add Key Color" button.
function renderChromaKeyEditor(l) {
  const wrap = document.getElementById('media-ck-colors');
  const addBtn = document.getElementById('media-ck-add');
  if (!wrap || !l.chroma || !Array.isArray(l.chroma.colors)) return;
  wrap.innerHTML = '';
  l.chroma.colors.forEach((key, idx) => {
    const chip = document.createElement('div');
    chip.style.cssText = 'display:flex; align-items:center; gap:6px;';

    const colorIn = document.createElement('input');
    colorIn.type = 'color';
    colorIn.value = key.c || '#00ff00';
    colorIn.style.cssText = 'width:28px; height:22px; padding:0; border:none; cursor:pointer; flex-shrink:0;';
    colorIn.oninput = e => { key.c = e.target.value; renderFrame(appState.time); };

    const tolIn = document.createElement('input');
    tolIn.type = 'range'; tolIn.min = '0'; tolIn.max = '1'; tolIn.step = '0.01';
    tolIn.value = key.t !== undefined ? key.t : 0.1;
    tolIn.style.flex = '1';
    const tolVal = document.createElement('span');
    tolVal.style.cssText = 'font-size:9px; color:#666; min-width:26px; text-align:right;';
    tolVal.innerText = Math.round((key.t !== undefined ? key.t : 0.1) * 100) + '%';
    tolIn.oninput = e => {
      key.t = parseFloat(e.target.value);
      tolVal.innerText = Math.round(key.t * 100) + '%';
      renderFrame(appState.time);
    };

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.innerText = '\\u2715';
    delBtn.title = 'Remove this key color';
    delBtn.style.cssText = 'font-size:10px; padding:1px 5px; background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; border-radius:4px; cursor:pointer; flex-shrink:0;';
    delBtn.onclick = () => {
      l.chroma.colors.splice(idx, 1);
      renderChromaKeyEditor(l);
      renderFrame(appState.time);
    };

    chip.appendChild(colorIn); chip.appendChild(tolIn); chip.appendChild(tolVal); chip.appendChild(delBtn);
    wrap.appendChild(chip);
  });
  if (addBtn) {
    addBtn.onclick = () => {
      l.chroma.colors.push({ c: '#00ff00', t: 0.1 });
      renderChromaKeyEditor(l);
      renderFrame(appState.time);
    };
  }
}

function smartRemoveCanvasBackground(srcCanvas, options = {}) {`);

// ------------------------------------------------------------------
// 14. Load-time migration for saved projects
// ------------------------------------------------------------------
subExact(
`document.getElementById('btn-save').onclick = () => {`,
`// Migrate layers from older save formats to the current data model
function migrateLoadedLayer(l) {
  // Chroma key: legacy single color { c, t } -> multi-color array
  if (l.chroma && !Array.isArray(l.chroma.colors)) {
    l.chroma = {
      en: !!l.chroma.en,
      colors: [{ c: l.chroma.c || '#00ff00', t: l.chroma.t !== undefined ? l.chroma.t : 0.1 }]
    };
  }
  // Live background removal defaults
  if (l.type === 'media' && !l.bgRemove) {
    l.bgRemove = { en: false, tolerance: 36 };
  }
}

document.getElementById('btn-save').onclick = () => {`);

subExact(
`  appState.layers = parsed.layers;`,
`  appState.layers = parsed.layers;
  appState.layers.forEach(migrateLoadedLayer);`);

// ------------------------------------------------------------------
// 15. Sheet grab handle: bigger hit area + grab cursor
// ------------------------------------------------------------------
subExact(
`    .sheet-grab {
      width: 36px; height: 4px; border-radius: 2px;
      background: rgba(255,255,255,0.3); margin: 2px auto 6px; flex-shrink: 0;
    }`,
`    .sheet-grab {
      width: 36px; height: 4px; border-radius: 2px;
      background: rgba(255,255,255,0.3); margin: 2px auto 6px; flex-shrink: 0;
      /* Enlarged invisible hit area for drag-to-resize */
      padding: 8px 0; background-clip: content-box;
      cursor: grab; touch-action: none;
    }
    .sheet-grab:active { cursor: grabbing; }`);

// ------------------------------------------------------------------
// 16. Sheet grab: pointer-drag resize of the bottom sheet
// ------------------------------------------------------------------
subExact(
`        setTimeout(() => document.getElementById(row.dataset.proxy)?.click(), 0);
      });
    });
  }`,
`        setTimeout(() => document.getElementById(row.dataset.proxy)?.click(), 0);
      });
    });

    // Drag-to-resize the sheet via the grab handle
    const sheetPanel = hudMoreSheet.querySelector('.sheet-panel');
    const sheetGrab = hudMoreSheet.querySelector('.sheet-grab');
    if (sheetPanel && sheetGrab) {
      let grabStartY = 0, grabStartH = 0, grabbing = false;
      sheetGrab.addEventListener('pointerdown', e => {
        grabbing = true;
        grabStartY = e.clientY;
        grabStartH = sheetPanel.getBoundingClientRect().height;
        sheetPanel.style.maxHeight = 'none';
        sheetPanel.style.height = grabStartH + 'px';
        try { sheetGrab.setPointerCapture(e.pointerId); } catch (err) {}
        e.preventDefault();
        e.stopPropagation();
      });
      sheetGrab.addEventListener('pointermove', e => {
        if (!grabbing) return;
        const maxH = window.innerHeight * 0.8; // 80dvh cap
        const newH = Math.max(120, Math.min(maxH, grabStartH + (grabStartY - e.clientY)));
        sheetPanel.style.height = newH + 'px';
      });
      const endGrab = () => { grabbing = false; };
      sheetGrab.addEventListener('pointerup', endGrab);
      sheetGrab.addEventListener('pointercancel', endGrab);
    }
  }`);

fs.writeFileSync(FILE, s, 'utf8');
console.log('OK — all 16 Phase 0.5 patches applied to index.html');

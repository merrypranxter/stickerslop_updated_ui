#!/usr/bin/env python3
"""Phase 3 — Layer-outline clipping masks + in-canvas text editing.

A. Layer-outline mask: l.mask.type = 'layer' + l.mask.sourceLayerId.
   Every layer's composited offscreen is stashed per frame (__layerFrameCache);
   a 'layer' mask thresholds the source's visible silhouette (buildImageMask,
   reused from the glitter engine) and applies it world-aligned via the
   existing destination-in path in applyLayerMask. Sources that render later
   in z-order (or are hidden) are rendered on demand, with a busy-set guard
   against circular mask references.
B. In-canvas text editing: dblclick a selected text layer -> positioned
   <textarea> matching the layer transform; live sync to l.text; Enter/blur
   commits (single undo step), Esc cancels.
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "index.html"
src = open(PATH, encoding="utf-8").read()

NL = chr(10)

def sub_exact(s, old, new, count=1, label=""):
    c = s.count(old)
    assert c == count, f"[{label}] anchor count {c} != {count}: {old[:70]!r}"
    return s.replace(old, new)

# ============================================================
# 1. Frame cache + silhouette helper + text editor — before applyLayerMask
# ============================================================
old = '''function applyLayerMask(targetCanvas, l) {'''
new = '''// --------------------------------------------------------
// LAYER-OUTLINE CLIPPING MASKS (PHASE 3)
// Every frame, each layer's composited offscreen (post mask/erase/crop) is
// stashed in __layerFrameCache. A layer with mask.type === 'layer' clips
// itself against another layer's visible silhouette (alpha-thresholded via
// buildImageMask, reused from the glitter engine), world-aligned so the mask
// tracks the source layer's transform. Sources that haven't rendered yet this
// frame (higher z-order, or hidden) are rendered on demand; the busy set
// guards against circular mask references.
// --------------------------------------------------------
const __layerFrameCache = new Map();
const __layerFrameBusy = new Set();

function getLayerMaskSilhouette(sourceId, targetLayer, time) {
  if (!sourceId || sourceId === targetLayer.id) return null;
  let entry = __layerFrameCache.get(sourceId);
  if (!entry) {
    const srcLayer = appState.layers.find(x => x.id === sourceId);
    if (!srcLayer || __layerFrameBusy.has(sourceId) || __layerFrameBusy.has(targetLayer.id)) return null;
    __layerFrameBusy.add(sourceId);
    __layerFrameBusy.add(targetLayer.id);
    try {
      const dims = getLayerDimensions(srcLayer);
      const scratch = document.createElement('canvas');
      scratch.width = Math.max(8, Math.ceil(dims.boxW) + 256);
      scratch.height = Math.max(8, Math.ceil(dims.boxH) + 256);
      const sg = scratch.getContext('2d');
      sg.translate(scratch.width / 2, scratch.height / 2);
      const wt0 = getLayerWorldTransform(srcLayer, time || 0);
      sg.rotate((wt0.rotation || 0) * Math.PI / 180);
      sg.scale(wt0.scaleX || 1, wt0.scaleY || 1);
      if (srcLayer.type === 'text') renderTextLayer(sg, srcLayer, time);
      else if (srcLayer.type === 'media') renderMediaLayer(sg, srcLayer, time);
      else if (srcLayer.type === 'sparkle') renderSparkleLayer(sg, srcLayer, time);
    } catch (err) {
      // never let a mask source break the frame
    } finally {
      __layerFrameBusy.delete(sourceId);
      __layerFrameBusy.delete(targetLayer.id);
    }
    entry = __layerFrameCache.get(sourceId);
  }
  if (!entry) return null;
  if (!entry.binary) entry.binary = buildImageMask(entry.canvas, 'alpha');
  return entry;
}
window.getLayerMaskSilhouette = getLayerMaskSilhouette;

// --------------------------------------------------------
// IN-CANVAS TEXT EDITING (PHASE 3)
// Double-click / double-tap a selected text layer to edit it in place: a
// positioned <textarea> matching the layer's live transform, synced to
// l.text on every keystroke. Enter or click-outside commits (one undo step
// for the whole edit); Esc cancels.
// --------------------------------------------------------
let __textEditState = null;

function closeTextEditor(commit) {
  const st = __textEditState;
  if (!st) return;
  __textEditState = null;
  const l = appState.layers.find(x => x.id === st.layerId);
  if (l) {
    l.text = commit ? st.ta.value : st.originalText;
    syncLayerLines(l);
  }
  window.removeEventListener('pointerdown', st.outsideHandler, true);
  st.ta.remove();
  renderFrame(appState.time);
  if (commit && typeof updateUI === 'function') updateUI();
}
window.closeTextEditor = closeTextEditor;

function openTextEditor(l) {
  if (!l || l.type !== 'text') return;
  if (__textEditState) closeTextEditor(true);
  pushUndoState('Edit Text');
  const rect = canvas.getBoundingClientRect();
  const wt = getLayerWorldTransform(l, appState.time);
  const sx = rect.width / canvas.width;
  const sy = rect.height / canvas.height;
  const dims = getLayerDimensions(l);
  const ta = document.createElement('textarea');
  ta.id = 'in-canvas-text-editor';
  ta.value = l.text !== undefined ? l.text : '';
  const cx = rect.left + wt.x * sx;
  const cy = rect.top + wt.y * sy;
  const wCss = Math.max(80, dims.boxW * sx * Math.abs(wt.scaleX || 1));
  const fontCss = Math.max(12, (l.size || 80) * sy * Math.abs(wt.scaleY || 1));
  ta.style.cssText = 'position:fixed; left:' + cx + 'px; top:' + cy + 'px; width:' + wCss + 'px; min-height:' + (fontCss * 1.6) + 'px;'
    + ' transform: translate(-50%,-50%) rotate(' + (wt.rotation || 0) + 'deg); z-index:9999;'
    + ' font-family:"' + (l.font || 'Impact') + '", sans-serif; font-size:' + fontCss + 'px; line-height:1.15;'
    + ' text-align:' + (l.align || 'center') + '; background:rgba(255,255,255,0.94); color:#111;'
    + ' border:2px dashed #0066ff; border-radius:8px; padding:8px; resize:none; outline:none; overflow:hidden;'
    + ' box-shadow:0 8px 30px rgba(0,0,0,0.25);';
  document.body.appendChild(ta);
  __textEditState = { layerId: l.id, ta: ta, originalText: ta.value, outsideHandler: null };
  ta.addEventListener('input', () => {
    const lay = appState.layers.find(x => x.id === (__textEditState && __textEditState.layerId));
    if (lay) {
      lay.text = ta.value;
      syncLayerLines(lay);
      renderFrame(appState.time);
    }
  });
  ta.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); closeTextEditor(true); }
    else if (e.key === 'Escape') { e.preventDefault(); closeTextEditor(false); }
  });
  const outsideHandler = e => { if (e.target !== ta) closeTextEditor(true); };
  __textEditState.outsideHandler = outsideHandler;
  window.addEventListener('pointerdown', outsideHandler, true);
  setTimeout(() => { ta.focus(); ta.select(); }, 0);
}
window.openTextEditor = openTextEditor;

function applyLayerMask(targetCanvas, l) {'''
src = sub_exact(src, old, new, 1, "phase3 helpers")

# ============================================================
# 2. applyLayerMask: time param + layer-silhouette branch
# ============================================================
old = '''function applyLayerMask(targetCanvas, l) {
  if (!l || !l.mask || !l.mask.en || !l.mask.type || l.mask.type === 'none') return;'''
new = '''function applyLayerMask(targetCanvas, l, time) {
  if (!l || !l.mask || !l.mask.en || !l.mask.type || l.mask.type === 'none') return;'''
src = sub_exact(src, old, new, 1, "applyLayerMask signature")

old = '''  mctx.fillStyle = '#ffffff';

  if (l.mask.type === 'line') {'''
new = '''  mctx.fillStyle = '#ffffff';

  if (l.mask.type === 'layer') {
    // Clip by another layer's outline: thresholded silhouette of the source
    // layer's visible pixels, world-aligned into this layer's mask space.
    const entry = getLayerMaskSilhouette(l.mask.sourceLayerId, l, time);
    if (!entry) { mctx.restore(); return; }
    const wt = getLayerWorldTransform(l, time || 0);
    const ws = entry.wTrans || wt;
    if (!wt.scaleX || !wt.scaleY) { mctx.restore(); return; }
    mctx.scale(1 / wt.scaleX, 1 / wt.scaleY);
    mctx.rotate(-(wt.rotation || 0) * Math.PI / 180);
    mctx.translate((ws.x || 0) - (wt.x || 0), (ws.y || 0) - (wt.y || 0));
    mctx.rotate((ws.rotation || 0) * Math.PI / 180);
    mctx.scale(ws.scaleX || 1, ws.scaleY || 1);
    mctx.translate(-entry.w / 2 - (entry.cropOx || 0), -entry.h / 2 - (entry.cropOy || 0));
    mctx.drawImage(entry.binary, 0, 0);
  } else if (l.mask.type === 'line') {'''
src = sub_exact(src, old, new, 1, "layer mask branch")

# ============================================================
# 3. renderLayers: clear the per-frame silhouette cache
# ============================================================
old = '''function renderLayers(targetCtx, time, isExport = false) {
  const layers = [...appState.layers].reverse();'''
new = '''function renderLayers(targetCtx, time, isExport = false) {
  __layerFrameCache.clear();
  const layers = [...appState.layers].reverse();'''
src = sub_exact(src, old, new, 1, "renderLayers cache clear")

# ============================================================
# 4. compositeLayerEffects: pass time to applyLayerMask + stash silhouette
# ============================================================
old = '''  if (l.mask && l.mask.en) {
    applyLayerMask(off, l);
  }'''
new = '''  if (l.mask && l.mask.en) {
    applyLayerMask(off, l, time);
  }'''
src = sub_exact(src, old, new, 1, "applyLayerMask time arg")

old = '''    cropOy = (cy2 + ch2 / 2 - 0.5) * eb.h;
  }

  // 2. SPEC COMPLIANT 2007 GLITTER ENGINE PASS FOR MEDIA'''
new = '''    cropOy = (cy2 + ch2 / 2 - 0.5) * eb.h;
  }

  // Phase 3: stash this layer's visible silhouette so other layers can clip
  // against it (mask.type === 'layer'). Reference only — the cache is cleared
  // at the start of every renderLayers pass.
  __layerFrameCache.set(l.id, { canvas: off, w: w, h: h, cropOx: cropOx, cropOy: cropOy, wTrans: getLayerWorldTransform(l, time), binary: null });

  // 2. SPEC COMPLIANT 2007 GLITTER ENGINE PASS FOR MEDIA'''
src = sub_exact(src, old, new, 1, "silhouette stash")

# ============================================================
# 5. Mask UI: 'Layer' shape button + source picker row
# ============================================================
old = '''                <button class="mask-shape-btn" data-shape="none" id="mask-btn-none"><span class="shape-icon">✕</span><span>Off</span></button>
              </div>
            </div>'''
new = '''                <button class="mask-shape-btn" data-shape="none" id="mask-btn-none"><span class="shape-icon">✕</span><span>Off</span></button>
                <button class="mask-shape-btn" data-shape="layer" id="mask-btn-layer"><span class="shape-icon">🧩</span><span>Layer</span></button>
              </div>
            </div>

            <!-- LAYER MASK SOURCE PICKER (PHASE 3) -->
            <div id="mask-layer-source-row" style="display:none; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:8px; flex-direction:column; gap:6px;">
              <label for="mask-layer-source" style="font-size:10px; font-weight:800; color:#166534;">🧩 CLIP TO LAYER OUTLINE</label>
              <select id="mask-layer-source" style="width:100%; padding:6px; border-radius:6px; border:1px solid #86efac; font-size:11px; font-weight:700;"></select>
              <div style="font-size:9px; color:#555; line-height:1.3;">This layer is clipped to the chosen layer's visible silhouette — move, rotate or scale the source and the mask follows. Hide the source (👁) for a pure clipping effect.</div>
            </div>'''
src = sub_exact(src, old, new, 1, "layer mask ui")

# ============================================================
# 6. renderMaskProperties: source picker binding (after crop bindings)
# ============================================================
old = '''  bindCropProp('crop-x', 'x', 'crop-x-val');
  bindCropProp('crop-y', 'y', 'crop-y-val');
  bindCropProp('crop-w', 'w', 'crop-w-val');
  bindCropProp('crop-h', 'h', 'crop-h-val');
'''
new = '''  bindCropProp('crop-x', 'x', 'crop-x-val');
  bindCropProp('crop-y', 'y', 'crop-y-val');
  bindCropProp('crop-w', 'w', 'crop-w-val');
  bindCropProp('crop-h', 'h', 'crop-h-val');

  // Layer-mask source picker (Phase 3)
  const layerMaskRow = document.getElementById('mask-layer-source-row');
  const layerMaskSel = document.getElementById('mask-layer-source');
  if (layerMaskRow && layerMaskSel) {
    const isLayerMask = l.mask.type === 'layer';
    layerMaskRow.style.display = isLayerMask ? 'flex' : 'none';
    if (isLayerMask) {
      const others = appState.layers.filter(x => x.id !== l.id);
      layerMaskSel.innerHTML = '';
      if (!others.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = '(no other layers)';
        layerMaskSel.appendChild(opt);
      }
      others.forEach(x => {
        const opt = document.createElement('option');
        opt.value = x.id;
        opt.textContent = (x.name || x.type) + ' — ' + x.type;
        layerMaskSel.appendChild(opt);
      });
      const stillValid = others.some(x => x.id === l.mask.sourceLayerId);
      if (!stillValid) l.mask.sourceLayerId = others.length ? others[0].id : null;
      layerMaskSel.value = l.mask.sourceLayerId || '';
      layerMaskSel.onchange = e => {
        l.mask.sourceLayerId = e.target.value || null;
        renderFrame(appState.time);
      };
    }
  }
'''
src = sub_exact(src, old, new, 1, "layer mask binding")

# ============================================================
# 7. dblclick wiring for in-canvas text editing
# ============================================================
old = '''canvas.addEventListener('pointerdown', e => handlePointerDown(e, true));'''
new = '''canvas.addEventListener('pointerdown', e => handlePointerDown(e, true));

// In-canvas text editing (Phase 3): double-click/double-tap a selected text layer
canvas.addEventListener('dblclick', e => {
  const l = appState.layers.find(x => x.id === appState.selectedId);
  if (!l || l.type !== 'text' || l.locked || !l.visible) return;
  e.preventDefault();
  openTextEditor(l);
});'''
src = sub_exact(src, old, new, 1, "dblclick wiring")

# ============================================================
open(PATH, "w", encoding="utf-8").write(src)
print("OK — Phase 3 patch applied,", len(src), "chars")

#!/usr/bin/env python3
"""Phase 2 — Eraser + non-destructive Crop for Sticker Slop Studio.

Eraser:
- l.eraseStrokes: JSON stroke data (undo/save friendly); destination-out canvas
  rebuilt+cached from strokes (getEraseMaskCanvas), applied in compositeLayerEffects
- New 'erase' tool mode (🧹 button / E key); one undo snapshot per stroke-end
  via the existing dragStartSnapshot/endPointerAction machinery
Crop:
- l.crop {en,x,y,w,h} normalized rect; destination-in clip inside
  compositeLayerEffects + re-centered origin (cropOx/cropOy shift every final
  composite drawImage). Fully non-destructive.
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
# 1. Helper functions — before the UNIFIED COMPOSITING PIPELINE header
# ============================================================
helpers = '''// --------------------------------------------------------
// ERASER ENGINE (PHASE 2)
// Strokes are stored as plain JSON data (l.eraseStrokes) so undo/redo and
// project save/load just work; the destination-out canvas is rebuilt (and
// cached) from them whenever the stroke data or the layer box changes.
// --------------------------------------------------------
function getEraseMaskCanvas(l, boxW, boxH) {
  const strokes = Array.isArray(l.eraseStrokes) ? l.eraseStrokes : [];
  let ptCount = 0;
  for (const s of strokes) ptCount += (s.pts ? s.pts.length : 0);
  const key = Math.round(boxW) + 'x' + Math.round(boxH) + ':' + strokes.length + ':' + ptCount;
  if (l._eraseCache && l._eraseCache.key === key) return l._eraseCache.canvas;
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(boxW));
  c.height = Math.max(1, Math.round(boxH));
  const g = c.getContext('2d');
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.fillStyle = '#ffffff';
  g.strokeStyle = '#ffffff';
  for (const s of strokes) {
    const size = Math.max(1, s.size || 24);
    const pts = s.pts || [];
    if (pts.length === 1) {
      g.beginPath();
      g.arc(pts[0][0], pts[0][1], size / 2, 0, Math.PI * 2);
      g.fill();
    } else if (pts.length > 1) {
      g.beginPath();
      g.lineWidth = size;
      g.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
      g.stroke();
    }
  }
  l._eraseCache = { key: key, canvas: c };
  return c;
}
window.getEraseMaskCanvas = getEraseMaskCanvas;

// Canvas point -> layer-local box coordinates (uncropped box space, matching
// the erase-stroke canvas). Accounts for crop re-centering when crop is on.
function canvasToLayerLocal(l, mx, my) {
  const rot = (l.rotation || 0) * Math.PI / 180;
  const dx = mx - l.x, dy = my - l.y;
  const lx = dx * Math.cos(-rot) - dy * Math.sin(-rot);
  const ly = dx * Math.sin(-rot) + dy * Math.cos(-rot);
  const dims = getLayerDimensions(l);
  let ox = 0, oy = 0;
  if (l.crop && l.crop.en) {
    const cw = Math.max(0.01, Math.min(1, (l.crop.w !== undefined ? l.crop.w : 1)));
    const ch = Math.max(0.01, Math.min(1, (l.crop.h !== undefined ? l.crop.h : 1)));
    const cx = Math.max(0, Math.min(1 - cw, l.crop.x || 0));
    const cy = Math.max(0, Math.min(1 - ch, l.crop.y || 0));
    ox = (cx + cw / 2 - 0.5) * dims.boxW;
    oy = (cy + ch / 2 - 0.5) * dims.boxH;
  }
  return {
    x: lx / (l.scaleX || 1) + dims.boxW / 2 + ox,
    y: ly / (l.scaleY || 1) + dims.boxH / 2 + oy
  };
}
window.canvasToLayerLocal = canvasToLayerLocal;

// --------------------------------------------------------
// UNIFIED COMPOSITING PIPELINE (PHASE 0)'''
old = '''// --------------------------------------------------------
// UNIFIED COMPOSITING PIPELINE (PHASE 0)'''
src = sub_exact(src, old, helpers, 1, "helpers")

# ============================================================
# 2. compositeLayerEffects: erase+crop block replaces Phase 0 erase hook
# ============================================================
old = '''  // Erase-mask hook (Phase 2): persistent hand-painted eraser canvas,
  // applied non-destructively after the mask, before the final composite.
  if (l.eraseMask) {
    octx.save();
    octx.globalCompositeOperation = 'destination-out';
    octx.drawImage(l.eraseMask, 0, 0, w, h);
    octx.restore();
  }'''
new = '''  // Erase-mask + Crop (Phase 2): persistent hand-painted strokes and a
  // non-destructive rectangle clip, applied after the shape mask, before the
  // final composite. Both live in the layer's logical box coordinate space
  // (uncropped getLayerDimensions box, centered on the layer origin) — for
  // text layers the render canvas is padded, so map through opts.eraseBox.
  const eb = (opts.eraseBox && opts.eraseBox.w > 0 && opts.eraseBox.h > 0) ? opts.eraseBox : { w: w, h: h };
  let eraseSrc = l.eraseMask || null;
  if (Array.isArray(l.eraseStrokes) && l.eraseStrokes.length) {
    eraseSrc = getEraseMaskCanvas(l, eb.w, eb.h);
  }
  if (eraseSrc) {
    octx.save();
    octx.globalCompositeOperation = 'destination-out';
    octx.drawImage(eraseSrc, (w - eb.w) / 2, (h - eb.h) / 2, eb.w, eb.h);
    octx.restore();
  }

  // Crop: rectangle clip + re-centered origin (cropOx/cropOy shift every
  // final composite so the crop rect's center becomes the layer origin).
  let cropOx = 0, cropOy = 0;
  if (l.crop && l.crop.en) {
    const cw2 = Math.max(0.01, Math.min(1, (l.crop.w !== undefined ? l.crop.w : 1)));
    const ch2 = Math.max(0.01, Math.min(1, (l.crop.h !== undefined ? l.crop.h : 1)));
    const cx2 = Math.max(0, Math.min(1 - cw2, l.crop.x || 0));
    const cy2 = Math.max(0, Math.min(1 - ch2, l.crop.y || 0));
    octx.save();
    octx.globalCompositeOperation = 'destination-in';
    octx.fillStyle = '#ffffff';
    octx.fillRect((w - eb.w) / 2 + cx2 * eb.w, (h - eb.h) / 2 + cy2 * eb.h, cw2 * eb.w, ch2 * eb.h);
    octx.restore();
    cropOx = (cx2 + cw2 / 2 - 0.5) * eb.w;
    cropOy = (cy2 + ch2 / 2 - 0.5) * eb.h;
  }'''
src = sub_exact(src, old, new, 1, "erase+crop block")

# ============================================================
# 3. Crop offsets on the 5 final-composite drawImage sites
# ============================================================
src = sub_exact(src,
  "      ctx.drawImage(activeFrame, -w / 2, -h / 2);",
  "      ctx.drawImage(activeFrame, -w / 2 - cropOx, -h / 2 - cropOy);",
  1, "glitter crop offset")
src = sub_exact(src,
  "    ctx.drawImage(off, -w/2 - baseDist + sliceShift, -h/2 + timeJitter);",
  "    ctx.drawImage(off, -w/2 - cropOx - baseDist + sliceShift, -h/2 - cropOy + timeJitter);",
  1, "glitch pass 1 crop offset")
src = sub_exact(src,
  "    ctx.drawImage(off, -w/2 + baseDist - sliceShift, -h/2 - timeJitter);",
  "    ctx.drawImage(off, -w/2 - cropOx + baseDist - sliceShift, -h/2 - cropOy - timeJitter);",
  1, "glitch pass 2 crop offset")
src = sub_exact(src,
  "    ctx.globalAlpha = baseOp;" + NL + "    ctx.drawImage(off, -w/2, -h/2);",
  "    ctx.globalAlpha = baseOp;" + NL + "    ctx.drawImage(off, -w/2 - cropOx, -h/2 - cropOy);",
  1, "glitch base crop offset")
src = sub_exact(src,
  "  } else {" + NL + "    ctx.save();" + NL + "    ctx.drawImage(off, -w/2, -h/2);",
  "  } else {" + NL + "    ctx.save();" + NL + "    ctx.drawImage(off, -w/2 - cropOx, -h/2 - cropOy);",
  1, "plain composite crop offset")

# ============================================================
# 4. renderTextLayer: pass eraseBox (unpadded logical box)
# ============================================================
src = sub_exact(src,
  "      compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: true });",
  "      compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: true, eraseBox: { w: maxWidth, h: totalHeight } });",
  1, "text fast-path eraseBox")
src = sub_exact(src,
  "  compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: hasGlitchAnim });",
  "  compositeLayerEffects(off, l, time, __targetCtx, { skipGlitter: true, skipGlitch: hasGlitchAnim, eraseBox: { w: maxWidth, h: totalHeight } });",
  1, "text tail eraseBox")

# ============================================================
# 5. Tool pill: erase button
# ============================================================
old = '''          <button id="tool-mode-pan" title="Pan Artboard (H / Spacebar)">✋ Hand / Pan Tool</button>'''
new = '''          <button id="tool-mode-pan" title="Pan Artboard (H / Spacebar)">✋ Hand / Pan Tool</button>
          <button id="tool-mode-erase" title="Erase on Selected Layer (E)">🧹 Erase Tool</button>'''
src = sub_exact(src, old, new, 1, "erase tool button")

# ============================================================
# 6. Erase tool bar (brush size + clear) — before ADD TEXT row
# ============================================================
old = '''      <div class="panel-section" style="display:flex; gap:6px;">
        <button id="btn-add-text" style="flex:1">ADD TEXT</button>'''
new = '''      <div class="panel-section" id="erase-tool-bar" style="display:none; padding:4px 12px; align-items:center; gap:8px;">
        <label style="font-size:10px; font-weight:800; color:#333; white-space:nowrap;">🧹 Brush</label>
        <input type="range" min="4" max="120" step="1" value="24" id="eraser-size" style="flex:1;">
        <span id="eraser-size-val" class="glitter-val-badge">24px</span>
        <button id="btn-erase-clear" type="button" title="Remove all eraser strokes from the selected layer" style="font-size:9px; font-weight:800; padding:2px 6px; cursor:pointer;">Clear</button>
      </div>
      <div class="panel-section" style="display:flex; gap:6px;">
        <button id="btn-add-text" style="flex:1">ADD TEXT</button>'''
src = sub_exact(src, old, new, 1, "erase tool bar")

# ============================================================
# 7. setInteractionMode: erase mode support
# ============================================================
old = '''function setInteractionMode(mode) {
  appViewport.mode = mode;
  const btnPan = document.getElementById('btn-toggle-hand');
  const btnTouchPan = document.getElementById('btn-touch-pan');
  const btnToolSelect = document.getElementById('tool-mode-select');
  const btnToolPan = document.getElementById('tool-mode-pan');
  
  const isPan = mode === 'pan';
  if (btnPan) btnPan.classList.toggle('active', isPan);
  if (btnTouchPan) btnTouchPan.classList.toggle('active', isPan);
  if (btnToolSelect) btnToolSelect.classList.toggle('active', !isPan);
  if (btnToolPan) btnToolPan.classList.toggle('active', isPan);
  
  applyViewportTransform(false);
}'''
new = '''function setInteractionMode(mode) {
  appViewport.mode = mode;
  const btnPan = document.getElementById('btn-toggle-hand');
  const btnTouchPan = document.getElementById('btn-touch-pan');
  const btnToolSelect = document.getElementById('tool-mode-select');
  const btnToolPan = document.getElementById('tool-mode-pan');
  const btnToolErase = document.getElementById('tool-mode-erase');
  const eraseBar = document.getElementById('erase-tool-bar');
  
  const isPan = mode === 'pan';
  const isErase = mode === 'erase';
  if (btnPan) btnPan.classList.toggle('active', isPan);
  if (btnTouchPan) btnTouchPan.classList.toggle('active', isPan);
  if (btnToolSelect) btnToolSelect.classList.toggle('active', !isPan && !isErase);
  if (btnToolPan) btnToolPan.classList.toggle('active', isPan);
  if (btnToolErase) btnToolErase.classList.toggle('active', isErase);
  if (eraseBar) eraseBar.style.display = isErase ? 'flex' : 'none';
  if (canvas) canvas.style.cursor = isErase ? 'crosshair' : '';
  
  applyViewportTransform(false);
}'''
src = sub_exact(src, old, new, 1, "setInteractionMode")

# ============================================================
# 8. Wiring: erase tool button, brush size, clear strokes
# ============================================================
old = '''  document.getElementById('tool-mode-pan')?.addEventListener('click', () => {
    setInteractionMode('pan');
  });'''
new = '''  document.getElementById('tool-mode-pan')?.addEventListener('click', () => {
    setInteractionMode('pan');
  });
  document.getElementById('tool-mode-erase')?.addEventListener('click', () => {
    setInteractionMode(appViewport.mode === 'erase' ? 'select' : 'erase');
  });

  // Eraser brush size + clear-strokes wiring (Phase 2)
  appState.eraserSize = appState.eraserSize || 24;
  const eraserSizeEl = document.getElementById('eraser-size');
  if (eraserSizeEl) {
    eraserSizeEl.value = appState.eraserSize;
    eraserSizeEl.oninput = e => {
      appState.eraserSize = parseFloat(e.target.value) || 24;
      const badge = document.getElementById('eraser-size-val');
      if (badge) badge.innerText = appState.eraserSize + 'px';
    };
  }
  document.getElementById('btn-erase-clear')?.addEventListener('click', () => {
    const l = appState.layers.find(x => x.id === appState.selectedId);
    if (l && Array.isArray(l.eraseStrokes) && l.eraseStrokes.length) {
      pushUndoState('Clear Eraser Strokes');
      l.eraseStrokes = [];
      renderFrame(appState.time);
      if (typeof showToast === 'function') showToast('🧹 Eraser strokes cleared', 2000);
    }
  });'''
src = sub_exact(src, old, new, 1, "erase wiring")

# ============================================================
# 9. handlePointerDown: erase stroke start
# ============================================================
old = '''  // 3. User clicked/touched on Canvas in Select Mode
  const rect = canvas.getBoundingClientRect();'''
new = '''  // 2b. Erase Tool: start a stroke on the selected layer
  if (appViewport.mode === 'erase') {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;
    const sel = appState.selectedId ? appState.layers.find(x => x.id === appState.selectedId) : null;
    if (!sel || sel.locked || !sel.visible) {
      if (typeof showToast === 'function') showToast('🧹 Select an unlocked layer first, then drag on the canvas to erase parts of it.', 3000);
      activeAction = null;
      applyViewportTransform(false);
      return;
    }
    dragStartSnapshot = getAppStateSnapshot();
    dragStartSnapshot.actionName = 'Erase Stroke';
    if (!Array.isArray(sel.eraseStrokes)) sel.eraseStrokes = [];
    const pt = canvasToLayerLocal(sel, mx, my);
    sel.eraseStrokes.push({ size: appState.eraserSize || 24, pts: [[pt.x, pt.y]] });
    activeAction = 'erase-stroke';
    canvas.style.cursor = 'crosshair';
    renderFrame(appState.time);
    return;
  }

  // 3. User clicked/touched on Canvas in Select Mode
  const rect = canvas.getBoundingClientRect();'''
src = sub_exact(src, old, new, 1, "erase pointerdown")

# ============================================================
# 10. pointermove: erase stroke continue
# ============================================================
old = '''  // Layer Manipulation
  if (!appState.selectedId || !initialLayerState) return;'''
new = '''  // Erase stroke in progress: append points (layer-local box space)
  if (activeAction === 'erase-stroke') {
    const l = appState.selectedId ? appState.layers.find(x => x.id === appState.selectedId) : null;
    if (l && Array.isArray(l.eraseStrokes) && l.eraseStrokes.length) {
      const pt = canvasToLayerLocal(l, currX, currY);
      const stroke = l.eraseStrokes[l.eraseStrokes.length - 1];
      const last = stroke.pts[stroke.pts.length - 1];
      if (Math.hypot(pt.x - last[0], pt.y - last[1]) >= 2) {
        stroke.pts.push([pt.x, pt.y]);
        renderFrame(appState.time);
      }
    }
    return;
  }

  // Layer Manipulation
  if (!appState.selectedId || !initialLayerState) return;'''
src = sub_exact(src, old, new, 1, "erase pointermove")

# ============================================================
# 11. Keyboard shortcut: E toggles erase tool
# ============================================================
old = '''  if (e.key === 'v' || e.key === 'V') {
    setInteractionMode('select');
    return;
  }'''
new = '''  if (e.key === 'v' || e.key === 'V') {
    setInteractionMode('select');
    return;
  }
  if (e.key === 'e' || e.key === 'E') {
    setInteractionMode(appViewport.mode === 'erase' ? 'select' : 'erase');
    return;
  }'''
src = sub_exact(src, old, new, 1, "E shortcut")

# ============================================================
# 12. Crop UI — top of the Mask inspector tab
# ============================================================
old = '''          <div class="prop-row" style="background:rgba(0,102,255,0.08); padding:8px; border-radius:6px; border:1px solid #b8d0f8; display:flex; align-items:center; justify-content:space-between;">
            <label for="mask-en" style="font-weight:800; color:#0055cc; cursor:pointer;">Enable Masking</label>'''
new = '''          <div style="font-size:10px; font-weight:800; color:#555; letter-spacing:0.05em; display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <span>✂️ CROP (NON-DESTRUCTIVE)</span>
          </div>
          <div class="prop-row" style="background:rgba(255,153,0,0.08); padding:8px; border-radius:6px; border:1px solid #ffd28a; display:flex; align-items:center; justify-content:space-between;">
            <label for="crop-en" style="font-weight:800; color:#b45309; cursor:pointer;">Enable Crop</label>
            <input type="checkbox" id="crop-en" style="width:18px; height:18px; cursor:pointer;">
          </div>
          <div id="crop-body" style="display:none; flex-direction:column; gap:6px; margin-bottom:4px;">
            <div class="prop-row"><label>Left</label><input type="range" min="0" max="1" step="0.01" value="0" id="crop-x" style="flex:1;"><span id="crop-x-val" class="glitter-val-badge">0%</span></div>
            <div class="prop-row"><label>Top</label><input type="range" min="0" max="1" step="0.01" value="0" id="crop-y" style="flex:1;"><span id="crop-y-val" class="glitter-val-badge">0%</span></div>
            <div class="prop-row"><label>Width</label><input type="range" min="0.05" max="1" step="0.01" value="1" id="crop-w" style="flex:1;"><span id="crop-w-val" class="glitter-val-badge">100%</span></div>
            <div class="prop-row"><label>Height</label><input type="range" min="0.05" max="1" step="0.01" value="1" id="crop-h" style="flex:1;"><span id="crop-h-val" class="glitter-val-badge">100%</span></div>
            <div style="font-size:9px; color:#888; line-height:1.3;">Clips the layer to the rectangle and re-centers it. Fully re-adjustable — nothing is discarded.</div>
          </div>
          <hr style="border:none; border-top:1px dashed #ccc; margin:2px 0 6px 0;">

          <div class="prop-row" style="background:rgba(0,102,255,0.08); padding:8px; border-radius:6px; border:1px solid #b8d0f8; display:flex; align-items:center; justify-content:space-between;">
            <label for="mask-en" style="font-weight:800; color:#0055cc; cursor:pointer;">Enable Masking</label>'''
src = sub_exact(src, old, new, 1, "crop ui")

# ============================================================
# 13. Crop bindings in renderMaskProperties (generic for all layer types)
# ============================================================
old = '''      flowerDepth: 0.65
    };
  }
'''
new = '''      flowerDepth: 0.65
    };
  }

  // Crop controls (Phase 2): non-destructive rectangle clip, all layer types
  if (!l.crop) l.crop = { en: false, x: 0, y: 0, w: 1, h: 1 };
  const cropEn = document.getElementById('crop-en');
  const cropBody = document.getElementById('crop-body');
  if (cropEn) {
    cropEn.checked = !!l.crop.en;
    cropEn.onchange = e => {
      pushUndoState('Toggle Crop');
      l.crop.en = e.target.checked;
      renderMaskProperties();
      renderFrame(appState.time);
    };
  }
  if (cropBody) cropBody.style.display = l.crop.en ? 'flex' : 'none';
  const bindCropProp = (id, key, badgeId) => {
    const el = document.getElementById(id);
    const badge = badgeId ? document.getElementById(badgeId) : null;
    if (!el) return;
    const v = l.crop[key] !== undefined ? l.crop[key] : ((key === 'w' || key === 'h') ? 1 : 0);
    el.value = v;
    if (badge) badge.innerText = Math.round(v * 100) + '%';
    el.oninput = e => {
      l.crop[key] = parseFloat(e.target.value);
      if (badge) badge.innerText = Math.round(l.crop[key] * 100) + '%';
      renderFrame(appState.time);
    };
  };
  bindCropProp('crop-x', 'x', 'crop-x-val');
  bindCropProp('crop-y', 'y', 'crop-y-val');
  bindCropProp('crop-w', 'w', 'crop-w-val');
  bindCropProp('crop-h', 'h', 'crop-h-val');
'''
src = sub_exact(src, old, new, 1, "crop bindings")

# ============================================================
open(PATH, "w", encoding="utf-8").write(src)
print("OK — Phase 2 patch applied,", len(src), "chars")

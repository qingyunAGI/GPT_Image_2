#!/usr/bin/env python3
"""
GPT-Image-2 图片生成器 - macOS 桌面应用（Web 版）
支持：多线程批量生成、自定义图片比例、质量选择、中断、实时预览
"""

import os
import sys
import json
import base64
import cgi
import time
import uuid
import tempfile
import threading
import subprocess
import webbrowser
import mimetypes
from urllib.parse import unquote, urlparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

# ==================== 常量 ====================
DEFAULT_SAVE_DIR = str(Path.home() / "Documents" / "GPT_IMAGE_2")
SETTINGS_PATH = Path.home() / ".gpt_image_2_settings.json"
API_KEY_ENV = "OPENAI_API_KEY"
ENDPOINT_ENV = "AZURE_OPENAI_IMAGE_ENDPOINT"
API_VERSION = os.environ.get("AZURE_OPENAI_IMAGE_API_VERSION", "2025-04-01-preview")
DEPLOYMENT = "gpt-image-2"
PORT = 8765
MAX_CONCURRENT = 10  # 同时最大并发（默认 = 用户一次最多生成的张数，无需额外限制）
MAX_IMAGES = 10      # 一次最多生成数量
MAX_INPUT_IMAGES = 16 # 一次最多上传参考图数量
MAX_INPUT_IMAGE_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_BODY_BYTES = MAX_INPUT_IMAGES * MAX_INPUT_IMAGE_BYTES + 5 * 1024 * 1024
MAX_JSON_BODY_BYTES = 256 * 1024
MIN_INTERVAL = 0     # 请求间最小间隔秒（0 = 不禁流，触发 429 就直接展示错误）

# 常用比例 → Azure GPT Image 系列支持的尺寸
RATIO_TO_SIZE = {
    "1:1":    "1024x1024",
    "16:9":   "1536x1024",
    "9:16":   "1024x1536",
    "4:3":    "1536x1024",
    "3:4":    "1024x1536",
    "3:2":    "1536x1024",
    "2:3":    "1024x1536",
    "21:9":   "1536x1024",
}

# ==================== HTML 界面 ====================
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GPT-Image-2 图片生成器</title>
<style>
  :root { --bg: #f5f5f7; --card: #fff; --text: #1d1d1f; --sub: #86868b; --accent: #007AFF; --border: #d2d2d7; --radius: 14px; --danger: #ff3b30; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 32px 20px; }
  .page-shell { width: min(1120px, 100%); margin: 0 auto; display: grid; grid-template-columns: 260px minmax(0, 760px); gap: 20px; align-items: start; justify-content: center; }
  .page-shell.history-collapsed { grid-template-columns: 52px minmax(0, 760px); }
  .app { width: 100%; display: flex; flex-direction: column; gap: 20px; }
  h1 { font-size: 28px; font-weight: 700; text-align: center; letter-spacing: -0.5px; }
  .subtitle { text-align: center; color: var(--sub); font-size: 14px; margin-top: -12px; }
  .env-badge { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 10px; font-size: 13px; font-weight: 500; }
  .env-badge.ok { background: #e8f8ee; color: #1a7f3f; }
  .env-badge.warn { background: #fff3e0; color: #b85d00; }
  .card { background: var(--card); border-radius: var(--radius); padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  textarea { width: 100%; border: 2px solid var(--border); border-radius: 10px; padding: 14px; font-size: 16px; font-family: inherit; resize: vertical; min-height: 80px; outline: none; transition: border-color 0.2s; }
  textarea:focus { border-color: var(--accent); }
  .hint { font-size: 12px; color: var(--sub); margin-top: 8px; }
  .upload-row { margin-top: 12px; display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; }
  .upload-box { border: 1.5px dashed var(--border); border-radius: 10px; padding: 10px 12px; background: #fafafa; cursor: pointer; color: var(--sub); font-size: 13px; transition: border-color 0.15s, background 0.15s; }
  .upload-box:hover { border-color: var(--accent); background: #f5f9ff; }
  .upload-box input { display: none; }
  .upload-preview { display: none; margin-top: 10px; grid-template-columns: repeat(auto-fill, minmax(86px, 1fr)); gap: 8px; }
  .upload-preview.show { display: grid; }
  .input-thumb { position: relative; aspect-ratio: 1 / 1; border-radius: 8px; overflow: hidden; background: #eee; border: 1px solid #e5e5ea; }
  .input-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .input-thumb span { position: absolute; left: 4px; right: 4px; bottom: 4px; background: rgba(0,0,0,0.58); color: #fff; font-size: 10px; padding: 2px 4px; border-radius: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .input-remove { position: absolute; top: 4px; right: 4px; width: 22px; height: 22px; border: none; border-radius: 50%; background: rgba(0,0,0,0.62); color: #fff; font-size: 16px; line-height: 20px; padding: 0; cursor: pointer; }
  .input-remove:hover { background: rgba(0,0,0,0.82); }
  .advanced-toggle { font-size: 13px; color: var(--accent); cursor: pointer; user-select: none; margin-top: 12px; display: inline-flex; align-items: center; gap: 6px; border: none; background: transparent; padding: 4px 0; font-family: inherit; font-weight: 600; }
  .advanced-toggle:hover { color: #005bbf; }
  .advanced-toggle .chevron { display: inline-block; min-width: 12px; text-align: center; font-size: 12px; line-height: 1; }
  .advanced { display: none; margin-top: 14px; padding-top: 14px; border-top: 1px solid #eee; }
  .advanced.show { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
  .field label { display: block; font-size: 12px; color: var(--sub); margin-bottom: 4px; font-weight: 500; }
  .field select, .field input { width: 100%; padding: 8px 10px; border: 1.5px solid var(--border); border-radius: 8px; font-size: 14px; font-family: inherit; outline: none; }
  .field select:focus, .field input:focus { border-color: var(--accent); }
  .btn-row { display: flex; gap: 10px; }
  .btn { padding: 12px 24px; border-radius: 10px; font-size: 15px; font-weight: 600; border: none; cursor: pointer; transition: all 0.15s; }
  .btn-primary { background: var(--accent); color: #fff; flex: 1; }
  .btn-primary:hover { background: #0066d6; }
  .btn-primary:disabled { background: #99caff; cursor: not-allowed; }
  .btn-secondary { background: #e8e8ed; color: var(--text); }
  .btn-secondary:hover { background: #dcdce2; }
  .btn-small { padding: 10px 14px; font-size: 13px; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-danger:hover { background: #d70015; }
  .history-sidebar { position: sticky; top: 24px; background: var(--card); border-radius: var(--radius); padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); max-height: calc(100vh - 48px); overflow: hidden; display: flex; flex-direction: column; }
  .history-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; min-height: 28px; }
  .tree-title-text { font-size: 13px; color: var(--sub); font-weight: 700; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .history-toggle { width: 28px; height: 28px; border: none; border-radius: 7px; background: #f2f2f7; color: #515154; cursor: pointer; font-family: inherit; font-size: 18px; line-height: 28px; padding: 0; flex: 0 0 auto; }
  .history-toggle:hover { background: #e8e8ed; color: var(--accent); }
  .history-body { overflow: auto; min-height: 260px; }
  .page-shell.history-collapsed .history-sidebar { padding: 10px; }
  .page-shell.history-collapsed .history-header { justify-content: center; margin-bottom: 0; }
  .page-shell.history-collapsed .tree-title-text,
  .page-shell.history-collapsed .history-body { display: none; }
  .tree-list { display: flex; flex-direction: column; gap: 2px; }
  .tree-row { width: 100%; display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 4px; align-items: center; border: none; background: transparent; color: #3a3a3c; border-radius: 7px; padding: 6px 7px; font-family: inherit; font-size: 13px; text-align: left; cursor: pointer; }
  .tree-row:hover { background: #f2f2f7; }
  .tree-row.active { background: #e8f0fe; color: #1a56db; font-weight: 700; }
  .tree-row.file { grid-template-columns: 18px minmax(0, 1fr); color: #515154; }
  .tree-row.file.active { background: #eef7ff; color: #1a56db; font-weight: 700; }
  .tree-spacer { width: 18px; }
  .tree-icon { width: 18px; text-align: center; color: var(--sub); font-size: 11px; }
  .tree-name { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .tree-count { font-size: 11px; color: var(--sub); }
  .tree-empty { color: #c4c4c9; font-size: 13px; padding: 24px 8px; text-align: center; }
  .gallery { background: var(--card); border-radius: var(--radius); box-shadow: 0 1px 3px rgba(0,0,0,0.06); min-height: 300px; max-height: min(720px, calc(100vh - 96px)); overflow: hidden; display: flex; flex-direction: column; }
  .gallery-head { padding: 14px 16px 10px; border-bottom: 1px solid #eee; display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .gallery-title { font-size: 14px; font-weight: 700; color: #3a3a3c; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .gallery-meta { font-size: 12px; color: var(--sub); flex: 0 0 auto; }
  .gallery-scroller { padding: 16px; overflow-y: auto; min-height: 260px; }
  .gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
  .gallery-grid img { width: 100%; border-radius: 8px; display: block; cursor: pointer; transition: transform 0.15s; }
  .gallery-grid img:hover { transform: scale(1.02); }
  .gallery-placeholder { color: #c4c4c9; font-size: 15px; text-align: center; padding: 60px 20px; }
  .thumb { position: relative; border-radius: 8px; overflow: hidden; background: #eee; }
  .thumb.selected { outline: 3px solid var(--accent); outline-offset: 3px; }
  .thumb .idx { position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.6); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 6px; font-weight: 600; }
  .thumb.loading::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, #eee 25%, #f5f5f5 50%, #eee 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; }
  .thumb-error { padding: 16px !important; flex-direction: column !important; gap: 8px; cursor: default; }
  .thumb-error .err-text { font-size: 12px; color: #c0392b; line-height: 1.5; word-break: break-word; max-height: 200px; overflow-y: auto; user-select: text; }
  .copy-btn { margin-top: 8px; padding: 5px 12px; font-size: 12px; background: #fff; border: 1px solid #ddd; border-radius: 6px; color: #555; cursor: pointer; transition: all 0.15s; }
  .copy-btn:hover { background: #f0f0f0; border-color: #bbb; }
  .copy-btn.copied { background: #e8f8ee; color: #1a7f3f; border-color: #1a7f3f; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
  .status { font-size: 13px; padding: 10px 16px; border-radius: 10px; }
  .status.ok { background: #e8f8ee; color: #1a7f3f; }
  .status.err { background: #ffeaea; color: #c0392b; }
  .status.info { background: #e8f0fe; color: #1a56db; }
  .progress-bar { height: 6px; background: #e5e5ea; border-radius: 3px; overflow: hidden; margin-top: 8px; }
  .progress-fill { height: 100%; background: var(--accent); width: 0; transition: width 0.3s; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .save-path { font-size: 12px; color: var(--sub); text-align: center; }
  .save-panel { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; grid-column: 1 / -1; }
  .save-panel label { display: block; font-size: 12px; color: var(--sub); margin-bottom: 5px; font-weight: 500; }
  .save-panel input { width: 100%; padding: 9px 10px; border: 1.5px solid var(--border); border-radius: 8px; font-size: 13px; font-family: inherit; color: #515154; background: #fafafa; overflow: hidden; text-overflow: ellipsis; }

  /* 大图弹窗 (Lightbox) */
  .lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 9999; display: none; align-items: center; justify-content: center; padding: 40px; animation: fadeIn 0.18s ease-out; }
  .lightbox.show { display: flex; }
  .lightbox img { max-width: 92vw; max-height: 88vh; border-radius: 10px; box-shadow: 0 20px 80px rgba(0,0,0,0.5); user-select: none; }
  .lightbox-close { position: absolute; top: 18px; right: 24px; background: rgba(255,255,255,0.12); color: #fff; border: none; width: 44px; height: 44px; border-radius: 50%; font-size: 24px; cursor: pointer; line-height: 44px; padding: 0; transition: background 0.15s; }
  .lightbox-close:hover { background: rgba(255,255,255,0.25); }
  .lightbox-info { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); color: #ddd; font-size: 13px; background: rgba(0,0,0,0.5); padding: 6px 16px; border-radius: 20px; pointer-events: none; }
  .lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.12); color: #fff; border: none; width: 52px; height: 52px; border-radius: 50%; font-size: 22px; cursor: pointer; padding: 0; line-height: 52px; transition: background 0.15s; }
  .lightbox-nav:hover { background: rgba(255,255,255,0.28); }
  .lightbox-prev { left: 24px; }
  .lightbox-next { right: 24px; }
  .modal { position: fixed; inset: 0; z-index: 10000; display: none; align-items: center; justify-content: center; padding: 24px; background: rgba(0,0,0,0.36); animation: fadeIn 0.16s ease-out; }
  .modal.show { display: flex; }
  .modal-panel { width: min(420px, 100%); background: #fff; border-radius: 12px; box-shadow: 0 24px 80px rgba(0,0,0,0.26); padding: 20px; }
  .modal-title { font-size: 18px; font-weight: 700; margin-bottom: 8px; }
  .modal-copy { font-size: 14px; line-height: 1.6; color: #515154; margin-bottom: 18px; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @media (max-width: 900px) {
    body { padding: 20px 14px; }
    .page-shell,
    .page-shell.history-collapsed { grid-template-columns: 1fr; gap: 14px; }
    .history-sidebar { position: static; max-height: 260px; }
    .history-body { min-height: 120px; }
    .page-shell.history-collapsed .history-sidebar { max-height: 48px; }
    .gallery { max-height: 68vh; }
  }
</style>
</head>
<body>
<div class="page-shell" id="pageShell">
  <aside class="history-sidebar" id="historyPanel">
    <div class="history-header">
      <span class="tree-title-text">历史照片</span>
      <button class="history-toggle" type="button" id="historyToggle" onclick="toggleHistoryPanel()" title="收起历史照片" aria-label="收起历史照片">‹</button>
    </div>
    <div class="history-body" id="historyTree">
      <div class="tree-empty">加载中...</div>
    </div>
  </aside>

  <div class="app">
    <h1>🎨 GPT-Image-2 图片生成器</h1>
    <p class="subtitle">输入关键词，AI 为你生成精美图片（支持多图并发）</p>

    <div id="envBadge" class="env-badge warn">检测中...</div>

    <div class="card">
      <textarea id="prompt" placeholder="输入图片描述关键词... 例如：A photograph of a red fox in an autumn forest"></textarea>
      <div class="upload-row">
        <label class="upload-box" for="inputImages">
          <input type="file" id="inputImages" accept="image/png,image/jpeg" multiple onchange="handleInputImages()">
          <span id="uploadLabel">可选：上传参考图 / 待编辑图片（PNG、JPG，最多 __MAX_INPUT_IMAGES__ 张）</span>
        </label>
        <button class="btn btn-secondary btn-small" type="button" onclick="clearInputImages()">清除</button>
      </div>
      <div class="upload-preview" id="uploadPreview"></div>
      <p class="hint">提示：不上传图片时为文生图；上传图片后会按提示词编辑或参考图片。Cmd+Enter 快速生成</p>
      <button class="advanced-toggle" type="button" id="advancedToggle" onclick="toggleAdvanced()" aria-expanded="true" aria-controls="advancedPanel">
        <span>⚙ 高级设置</span><span class="chevron" id="advancedChevron">▲</span>
      </button>
      <div class="advanced show" id="advancedPanel">
        <div class="field">
          <label>图片比例</label>
          <select id="ratio">
            <option value="1:1">1:1 方形</option>
            <option value="16:9">16:9 横屏</option>
            <option value="9:16">9:16 竖屏</option>
            <option value="4:3">4:3 横屏</option>
            <option value="3:4">3:4 竖屏</option>
            <option value="3:2">3:2 横屏</option>
            <option value="2:3">2:3 竖屏</option>
            <option value="21:9">21:9 超宽</option>
          </select>
        </div>
        <div class="field">
          <label>生成质量</label>
          <select id="quality">
            <option value="medium">Medium（推荐）</option>
            <option value="low">Low</option>
            <option value="high">High</option>
          </select>
        </div>
        <div class="field">
          <label>生成数量</label>
          <input type="number" id="count" value="1" min="1" max="__MAX__">
        </div>
        <div class="save-panel">
          <div>
            <label for="saveDirInput">保存目录</label>
            <input id="saveDirInput" type="text" readonly value="SAVE_DIR_PLACEHOLDER">
          </div>
          <button class="btn btn-secondary btn-small" type="button" id="chooseFolderBtn" onclick="chooseFolder()">选择目录</button>
        </div>
      </div>
    </div>

    <div class="btn-row">
      <button class="btn btn-primary" id="genBtn" onclick="startGenerate()">🎨 生成图片</button>
      <button class="btn btn-secondary" onclick="openFolder()" title="生成中也可以使用">📁 打开目录</button>
    </div>

    <div class="gallery" id="gallery">
      <p class="gallery-placeholder">生成的图片将在此处预览</p>
    </div>

    <div class="status info" id="status">就绪</div>
    <div id="progressWrap" style="display:none;">
      <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
      <div style="font-size:12px; color:var(--sub); margin-top:4px;" id="progressText">0 / 0</div>
    </div>
  </div>
</div>

<!-- 大图弹窗 -->
<div class="lightbox" id="lightbox" onclick="closeLightbox(event)">
  <button class="lightbox-close" onclick="closeLightbox(event, true)" title="关闭 (ESC)">×</button>
  <button class="lightbox-nav lightbox-prev" onclick="navLightbox(event, -1)" title="上一张 (←)">‹</button>
  <img id="lightbox-img" src="" alt="大图预览">
  <button class="lightbox-nav lightbox-next" onclick="navLightbox(event, 1)" title="下一张 (→)">›</button>
  <div class="lightbox-info" id="lightbox-info">点击空白处或按 ESC 关闭</div>
</div>

<!-- 中断确认弹窗 -->
<div class="modal" id="cancelModal" onclick="closeCancelModal(event)">
  <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="cancelModalTitle" onclick="event.stopPropagation()">
    <div class="modal-title" id="cancelModalTitle">中断当前任务？</div>
    <div class="modal-copy">已经完成的图片会保留，正在生成中的请求会尽量停止。中断后可以修改提示词或参数再重新生成。</div>
    <div class="modal-actions">
      <button class="btn btn-secondary btn-small" type="button" onclick="closeCancelModal(null, true)">继续等待</button>
      <button class="btn btn-danger btn-small" type="button" id="confirmCancelBtn" onclick="confirmCancelGenerate()">中断任务</button>
    </div>
  </div>
</div>

<script>
let currentJob = null;
let pollTimer = null;
let generating = false;
let _galleryUrls = [];        // 最近一次 gallery 的图片 URL 列表（供弹窗使用）
let _galleryErrors = [];      // 最近一次 gallery 的错误信息列表
let _lightboxIndex = 0;
const MAX_INPUT_IMAGES = __MAX_INPUT_IMAGES__;
const CSRF_TOKEN = "__CSRF_TOKEN__";
let inputImageFiles = [];
let inputImageSeq = 0;
let historyImages = [];
let historyTree = null;
let activeFolder = '__all__';
let expandedTreeFolders = new Set(['__all__']);
let historyCollapsed = false;
let selectedImageRel = '';

function saveSettings() {
  try {
    localStorage.setItem('gptimg.prompt', document.getElementById('prompt').value);
    localStorage.setItem('gptimg.ratio', document.getElementById('ratio').value);
    localStorage.setItem('gptimg.quality', document.getElementById('quality').value);
    localStorage.setItem('gptimg.count', document.getElementById('count').value);
  } catch (e) {}
}
function loadSettings() {
  try {
    const p = localStorage.getItem('gptimg.prompt');
    if (p) document.getElementById('prompt').value = p;
    const r = localStorage.getItem('gptimg.ratio');
    if (r) document.getElementById('ratio').value = r;
    const q = localStorage.getItem('gptimg.quality');
    if (q) document.getElementById('quality').value = q;
    const c = localStorage.getItem('gptimg.count');
    if (c) document.getElementById('count').value = c;
    historyCollapsed = localStorage.getItem('gptimg.historyCollapsed') === '1';
    applyHistoryCollapsed(historyCollapsed, false);
  } catch (e) {}
}
async function loadRecentImages(options) {
  const opts = options || {};
  const updateGallery = opts.updateGallery !== false;
  const showLoadedStatus = opts.showLoadedStatus !== false;
  try {
    const r = await fetch('/api/images');
    const d = await r.json();
    historyImages = d.images || [];
    historyTree = d.tree || null;
    if (selectedImageRel && !historyImages.some(img => img.rel === selectedImageRel)) {
      selectedImageRel = '';
    }
    if (activeFolder !== '__all__' && !historyImages.some(img => img.folder === activeFolder || (activeFolder && img.folder && img.folder.startsWith(activeFolder + '/')))) {
      activeFolder = '__all__';
    }
    seedExpandedFolders(historyTree);
    renderHistoryTree();
    if (updateGallery && historyImages.length > 0) {
      renderCurrentHistoryGallery();
      if (showLoadedStatus) setStatus('已加载 ' + historyImages.length + ' 张历史图片，可继续生成新图片', 'ok');
    } else if (updateGallery) {
      renderGallery([]);
    }
  } catch (e) {
    historyImages = [];
    historyTree = null;
    renderHistoryTree();
    if (updateGallery) renderGallery([]);
  }
}
async function checkEnv() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    const badge = document.getElementById('envBadge');
    if (d.api_ready) {
      badge.className = 'env-badge ok';
      badge.textContent = '\u2705 API 已就绪 | ' + d.endpoint_domain;
    } else {
      badge.className = 'env-badge warn';
      badge.textContent = '\u26a0\ufe0f ' + d.message;
    }
  } catch (e) {}
}

function setSaveDir(path) {
  const input = document.getElementById('saveDirInput');
  if (input) input.value = path || '';
}

async function loadServerSettings() {
  try {
    const r = await fetch('/api/settings');
    const d = await r.json();
    if (d.save_dir) setSaveDir(d.save_dir);
  } catch (e) {}
}

async function handleInputImages() {
  const input = document.getElementById('inputImages');
  const selectedFiles = Array.from(input.files || []);
  input.value = '';
  if (selectedFiles.length === 0) {
    updateInputImagePreview();
    return;
  }

  let added = 0;
  let skipped = 0;
  for (const file of selectedFiles) {
    if (inputImageFiles.length >= MAX_INPUT_IMAGES) {
      skipped++;
      continue;
    }
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setStatus('只支持 PNG 或 JPG 图片', 'err');
      skipped++;
      continue;
    }
    if (file.size > 50 * 1024 * 1024) {
      setStatus('单张输入图片不能超过 50MB', 'err');
      skipped++;
      continue;
    }
    inputImageFiles.push({
      id: ++inputImageSeq,
      file: file,
      url: URL.createObjectURL(file),
    });
    added++;
  }
  updateInputImagePreview();
  if (skipped > 0 && inputImageFiles.length >= MAX_INPUT_IMAGES) {
    setStatus(`最多保留 ${MAX_INPUT_IMAGES} 张输入图片，已忽略多余图片`, 'info');
  } else if (added > 0) {
    setStatus(`已添加 ${added} 张输入图片，共 ${inputImageFiles.length} 张`, 'ok');
  }
}

function escapeHtml(text) {
  return String(text || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function updateInputImagePreview() {
  const preview = document.getElementById('uploadPreview');
  if (inputImageFiles.length === 0) {
    preview.innerHTML = '';
    preview.classList.remove('show');
    document.getElementById('uploadLabel').textContent = `可选：上传参考图 / 待编辑图片（PNG、JPG，最多 ${MAX_INPUT_IMAGES} 张）`;
    return;
  }
  preview.innerHTML = inputImageFiles.map(item => {
    const safeName = escapeHtml(item.file.name);
    return `<div class="input-thumb"><img src="${item.url}" alt="${safeName}"><button class="input-remove" type="button" title="移除" onclick="removeInputImage(${item.id})">×</button><span>${safeName}</span></div>`;
  }).join('');
  preview.classList.add('show');
  document.getElementById('uploadLabel').textContent = `已选择 ${inputImageFiles.length} / ${MAX_INPUT_IMAGES} 张输入图片，可继续追加`;
}

function removeInputImage(id) {
  const idx = inputImageFiles.findIndex(item => item.id === id);
  if (idx < 0) return;
  URL.revokeObjectURL(inputImageFiles[idx].url);
  inputImageFiles.splice(idx, 1);
  updateInputImagePreview();
}

function clearInputImages() {
  const input = document.getElementById('inputImages');
  input.value = '';
  inputImageFiles.forEach(item => URL.revokeObjectURL(item.url));
  inputImageFiles = [];
  updateInputImagePreview();
}

function toggleAdvanced() {
  const panel = document.getElementById('advancedPanel');
  const expanded = panel.classList.toggle('show');
  document.getElementById('advancedToggle').setAttribute('aria-expanded', expanded ? 'true' : 'false');
  document.getElementById('advancedChevron').textContent = expanded ? '▲' : '▼';
}

function toggleHistoryPanel() {
  applyHistoryCollapsed(!historyCollapsed, true);
}

function applyHistoryCollapsed(collapsed, persist) {
  historyCollapsed = collapsed;
  const shell = document.getElementById('pageShell');
  const btn = document.getElementById('historyToggle');
  if (shell) shell.classList.toggle('history-collapsed', collapsed);
  if (btn) {
    btn.textContent = collapsed ? '›' : '‹';
    btn.title = collapsed ? '打开历史照片' : '收起历史照片';
    btn.setAttribute('aria-label', collapsed ? '打开历史照片' : '收起历史照片');
  }
  if (persist) {
    try { localStorage.setItem('gptimg.historyCollapsed', collapsed ? '1' : '0'); } catch (e) {}
  }
}

function setStatus(msg, cls) {
  const s = document.getElementById('status');
  s.textContent = msg;
  s.className = 'status ' + cls;
}

function seedExpandedFolders(tree) {
  expandedTreeFolders = new Set(['__all__']);
  if (!tree || !tree.children) return;
  const firstFolder = tree.children.find(node => node.type === 'folder' && node.folder);
  const rootFolder = tree.children.find(node => node.type === 'folder' && node.folder === '');
  if (rootFolder) expandedTreeFolders.add(rootFolder.id);
  if (firstFolder) expandedTreeFolders.add(firstFolder.id);
}

function renderHistoryTree() {
  const container = document.getElementById('historyTree');
  if (!container) return;
  if (!historyTree || !historyImages.length) {
    container.innerHTML = '<div class="tree-empty">暂无历史图片</div>';
    return;
  }
  let html = '<div class="tree-list">';
  html += renderTreeNode(historyTree, 0);
  html += '</div>';
  container.innerHTML = html;
}

function renderTreeNode(node, depth) {
  const isFile = node.type === 'file';
  const id = escapeHtml(node.id || '');
  const name = escapeHtml(node.name || '');
  const count = Number(node.count || 0);
  const indent = depth * 14;
  if (isFile) {
    const active = selectedImageRel && selectedImageRel === node.rel;
    return `<button class="tree-row file ${active ? 'active' : ''}" style="padding-left:${indent + 7}px" type="button" title="${name}" data-id="${id}" onclick="selectTreeFile(this.dataset.id)"><span class="tree-icon">□</span><span class="tree-name">${name}</span></button>`;
  }
  const expanded = expandedTreeFolders.has(node.id);
  const active = activeFolder === (node.folder === undefined ? '__all__' : node.folder);
  const chevron = (node.children && node.children.length) ? (expanded ? '▼' : '▶') : '';
  let html = `<button class="tree-row ${active ? 'active' : ''}" style="padding-left:${indent + 7}px" type="button" title="${name}" data-id="${id}" onclick="selectTreeFolder(this.dataset.id)"><span class="tree-icon">${chevron}</span><span class="tree-name">${name}</span><span class="tree-count">${count}</span></button>`;
  if (expanded && node.children && node.children.length) {
    node.children.forEach(child => { html += renderTreeNode(child, depth + 1); });
  }
  return html;
}

function findTreeNodeById(id, node) {
  if (!node) return null;
  if (node.id === id) return node;
  for (const child of (node.children || [])) {
    const found = findTreeNodeById(id, child);
    if (found) return found;
  }
  return null;
}

function selectTreeFolder(id) {
  const node = findTreeNodeById(id, historyTree);
  if (!node || node.type === 'file') return;
  if (node.children && node.children.length) {
    if (expandedTreeFolders.has(node.id)) expandedTreeFolders.delete(node.id);
    else expandedTreeFolders.add(node.id);
  }
  activeFolder = node.folder === undefined ? '__all__' : node.folder;
  selectedImageRel = '';
  renderHistoryTree();
  renderCurrentHistoryGallery();
}

function selectTreeFile(id) {
  const node = findTreeNodeById(id, historyTree);
  if (!node || !node.rel) return;
  const img = historyImages.find(item => item.rel === node.rel);
  if (!img) return;
  activeFolder = img.folder || '';
  selectedImageRel = img.rel;
  expandedTreeFolders.add('__all__');
  expandTreePath(activeFolder);
  renderHistoryTree();
  renderCurrentHistoryGallery();
  setStatus('已选中图片，可在右侧预览区点击缩略图查看大图', 'info');
  requestAnimationFrame(() => {
    const target = document.querySelector(`.thumb[data-rel="${cssEscape(selectedImageRel)}"]`);
    if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
}

function expandTreePath(folder) {
  if (!folder) {
    expandedTreeFolders.add('folder:');
    return;
  }
  const parts = folder.split('/');
  for (let i = 1; i <= parts.length; i++) {
    expandedTreeFolders.add('folder:' + parts.slice(0, i).join('/'));
  }
}

function cssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, '\\$&');
}

function renderCurrentHistoryGallery() {
  let images = historyImages;
  if (activeFolder !== '__all__') {
    images = historyImages.filter(img => img.folder === activeFolder || (activeFolder && img.folder && img.folder.startsWith(activeFolder + '/')));
  }
  const meta = getActiveGalleryMeta(images.length);
  renderGallery(images, meta);
}

function getActiveGalleryMeta(count) {
  const node = activeFolder === '__all__' ? historyTree : findTreeNodeById('folder:' + activeFolder, historyTree);
  const title = node && node.name ? node.name : '全部历史';
  return {
    title: activeFolder === '__all__' ? '全部历史' : title,
    count: count,
  };
}

let _gallerySignature = '';  // 上一次 gallery 的状态签名（用于增量更新）

function renderGallery(images, meta) {
  const gallery = document.getElementById('gallery');
  const header = meta ? `<div class="gallery-head"><div class="gallery-title" title="${escapeHtml(meta.title)}">${escapeHtml(meta.title)}</div><div class="gallery-meta">${Number(meta.count || 0)} 张</div></div>` : '';
  if (!images || images.length === 0) {
    const emptyText = meta ? '当前文件夹暂无图片' : '生成的图片将在此处预览';
    gallery.innerHTML = header + `<div class="gallery-scroller"><p class="gallery-placeholder">${emptyText}</p></div>`;
    _galleryUrls = [];
    _galleryErrors = [];
    _gallerySignature = '';
    return;
  }
  // 增量更新：计算每张图片的"状态签名"，只有变化时才重建
  // 签名格式: done|url|error 用 "||" 连接，再用 "###" 分隔每张
  const currentSig = images.map(img => {
    if (!img) return '';
    if (img.done && img.url) return 'D:' + img.url + ':' + (selectedImageRel === img.rel ? 'S' : '');
    if (img.error) return 'E:' + img.error;
    return 'L:';  // 加载中
  }).join('###') + '::' + (meta ? `${meta.title}|${meta.count}` : '');
  // 1) 总数量没变 + 每张的最终状态(done/error)没变 → 完全跳过重建（避免已完成图片闪烁）
  // 2) 只有加载中→完成 / 加载中→失败 的"变化"才需要重建对应位置
  if (currentSig === _gallerySignature) return;  // 完全无变化，跳过
  _gallerySignature = currentSig;

  _galleryUrls = images.map(img => (img && img.done && img.url) ? img.url : null);
  _galleryErrors = images.map(img => (img && img.error) ? img.error : null);

  let html = header + '<div class="gallery-scroller"><div class="gallery-grid">';
  images.forEach((img, i) => {
    if (img.done && img.url) {
      // 关键：不再附加 ?t= 时间戳。文件名本身已含时间戳，浏览器可以安全缓存，
      // 这样已完成的图片不会因为重建 DOM 而闪烁。
      const label = escapeHtml(img.folder ? img.folder : ('#' + (i + 1)));
      const rel = escapeHtml(img.rel || '');
      const selected = selectedImageRel && img.rel === selectedImageRel;
      html += `<div class="thumb ${selected ? 'selected' : ''}" data-rel="${rel}"><span class="idx">${label}</span><img src="${img.url}" alt="image ${i+1}" onclick="openLightbox(${i})"></div>`;
    } else if (img.error) {
      const safeErr = img.error.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      html += `<div class="thumb thumb-error" data-err="${safeErr}"><span class="idx">#${i + 1}</span><div class="err-text">\u274c ${safeErr}</div><button class="copy-btn" data-idx="${i}" onclick="copyErrorText(${i}, this)">复制错误</button></div>`;
    } else {
      html += `<div class="thumb loading" style="aspect-ratio:1/1;"><span class="idx">#${i + 1}</span></div>`;
    }
  });
  html += '</div></div>';
  gallery.innerHTML = html;
}

/* ========== 复制单张图片的错误信息 ========== */
function copyErrorText(index, btn) {
  const err = _galleryErrors[index];
  if (!err) return;
  if (!btn) btn = document.querySelector(`.copy-btn[data-idx="${index}"]`);
  const doFlash = () => {
    if (!btn) return;
    const oldText = btn.textContent;
    btn.textContent = '已复制 ✓';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = oldText;
      btn.classList.remove('copied');
    }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(err).then(doFlash).catch(() => fallbackCopy(err, btn, doFlash));
  } else {
    fallbackCopy(err, btn, doFlash);
  }
}
function fallbackCopy(text, btn, onDone) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed'; ta.style.top = '-1000px'; ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); onDone(); } catch (e) { alert('复制失败，请手动选择文本'); }
  document.body.removeChild(ta);
}

/* ========== 大图弹窗 ========== */
function openLightbox(index) {
  const url = _galleryUrls[index];
  if (!url) return;
  _lightboxIndex = index;
  document.getElementById('lightbox-img').src = url + '?t=' + Date.now();
  _updateLightboxInfo();
  document.getElementById('lightbox').classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeLightbox(event, force) {
  // 点击图片本身不关闭；点击背景/按钮才关闭
  if (!force && event && event.target && event.target.tagName === 'IMG') return;
  document.getElementById('lightbox').classList.remove('show');
  document.body.style.overflow = '';
}

function navLightbox(event, direction) {
  event.stopPropagation();
  // 在 _galleryUrls 里找下一张可用的图
  let i = _lightboxIndex;
  for (let step = 0; step < _galleryUrls.length; step++) {
    i = (i + direction + _galleryUrls.length) % _galleryUrls.length;
    if (_galleryUrls[i]) {
      _lightboxIndex = i;
      document.getElementById('lightbox-img').src = _galleryUrls[i] + '?t=' + Date.now();
      _updateLightboxInfo();
      return;
    }
  }
}

function _updateLightboxInfo() {
  // 统计当前是所有可用图片的第几张
  const available = _galleryUrls.filter(u => u).length;
  const before = _galleryUrls.slice(0, _lightboxIndex).filter(u => u).length;
  document.getElementById('lightbox-info').textContent = `第 ${before + 1} / ${available} 张  ·  点击空白 / ESC 关闭`;
}

// ESC 关闭弹窗，← → 切换
document.addEventListener('keydown', function(e) {
  const cancelModal = document.getElementById('cancelModal');
  if (cancelModal.classList.contains('show')) {
    if (e.key === 'Escape') closeCancelModal(null, true);
    return;
  }
  const lb = document.getElementById('lightbox');
  if (!lb.classList.contains('show')) return;
  if (e.key === 'Escape') { closeLightbox(null, true); }
  else if (e.key === 'ArrowLeft') { navLightbox({stopPropagation:()=>{}}, -1); }
  else if (e.key === 'ArrowRight') { navLightbox({stopPropagation:()=>{}}, 1); }
});

function updateProgress(completed, total, errors) {
  const wrap = document.getElementById('progressWrap');
  const fill = document.getElementById('progressFill');
  const txt = document.getElementById('progressText');
  if (total > 0) {
    wrap.style.display = 'block';
    const pct = Math.round((completed / total) * 100);
    fill.style.width = pct + '%';
    txt.textContent = `完成 ${completed} / ${total}${errors > 0 ? '  |  失败 ' + errors : ''}`;
  } else {
    wrap.style.display = 'none';
  }
}

async function startGenerate() {
  if (generating) return;
  saveSettings();
  const prompt = document.getElementById('prompt').value.trim();
  if (!prompt) { setStatus('请输入图片描述关键词', 'err'); return; }
  const fileInput = document.getElementById('inputImages');
  if ((fileInput.files || []).length > 0 && inputImageFiles.length === 0) {
    await handleInputImages();
  }

  const count = Math.min(Math.max(1, parseInt(document.getElementById('count').value) || 1), __MAX__);
  const actionText = inputImageFiles.length > 0 ? '编辑' : '生成';

  generating = true;
  const btn = document.getElementById('genBtn');
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>${actionText}中...`;
  setStatus(`正在启动多线程${actionText}任务...`, 'info');

  // 初始化占位 gallery
  const placeholders = [];
  for (let i = 0; i < count; i++) placeholders.push({});
  renderGallery(placeholders);
  updateProgress(0, count, 0);

  try {
    const form = new FormData();
    form.append('prompt', prompt);
    form.append('ratio', document.getElementById('ratio').value);
    form.append('quality', document.getElementById('quality').value);
    form.append('count', String(count));
    inputImageFiles.forEach(item => form.append('input_images', item.file, item.file.name));

    const r = await fetch('/api/generate', {
      method: 'POST',
      headers: {'X-CSRF-Token': CSRF_TOKEN},
      body: form
    });
    const d = await r.json();
    if (d.error) {
      setStatus('\u274c ' + d.error, 'err');
      stopGenUI();
      return;
    }
    currentJob = d.job_id;
    setStatus(`\u23f3 任务已提交，正在并发${actionText} ${count} 张... (点击下方中断按钮可停止)`, 'info');

    // 显示中断按钮
    btn.className = 'btn btn-danger';
    btn.innerHTML = '\u23f9\ufe0f 中断生成';
    btn.disabled = false;
    btn.onclick = cancelGenerate;

    // 开始轮询进度
    pollTimer = setInterval(pollProgress, 1500);
    pollProgress();
  } catch(e) {
    setStatus('\u274c 网络错误: ' + e.message, 'err');
    stopGenUI();
  }
}

async function pollProgress() {
  if (!currentJob) return;
  try {
    const r = await fetch('/api/job/' + currentJob);
    const d = await r.json();
    renderGallery(d.images);
    updateProgress(d.completed, d.total, d.errors);
    setStatus(d.status_text, d.status_text.includes('\u274c') ? 'err' : (d.done ? 'ok' : 'info'));

    if (d.done) {
      clearInterval(pollTimer);
      pollTimer = null;
      currentJob = null;
      stopGenUI();
      const ok = d.completed - d.errors;
      await loadRecentImages({updateGallery: false, showLoadedStatus: false});
      setStatus(`\u2705 任务完成！成功 ${ok} 张${d.errors > 0 ? '，失败 ' + d.errors : ''}`, 'ok');
    }
  } catch(e) {
    console.error(e);
  }
}

async function cancelGenerate() {
  if (!currentJob) return;
  openCancelModal();
}

function openCancelModal() {
  const modal = document.getElementById('cancelModal');
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  setTimeout(() => document.getElementById('confirmCancelBtn').focus(), 0);
}

function closeCancelModal(event, force) {
  if (!force && event && event.target && event.target.id !== 'cancelModal') return;
  document.getElementById('cancelModal').classList.remove('show');
  document.body.style.overflow = '';
}

async function confirmCancelGenerate() {
  if (!currentJob) {
    closeCancelModal(null, true);
    return;
  }
  const btn = document.getElementById('confirmCancelBtn');
  btn.disabled = true;
  btn.textContent = '中断中...';
  try {
    await fetch('/api/job/' + currentJob + '/cancel', {
      method: 'POST',
      headers: {'X-CSRF-Token': CSRF_TOKEN}
    });
  } catch(e) {}
  closeCancelModal(null, true);
  btn.disabled = false;
  btn.textContent = '中断任务';
  clearInterval(pollTimer);
  pollTimer = null;
  currentJob = null;
  stopGenUI();
  setStatus('\u2705 已中断', 'ok');
}

function stopGenUI() {
  generating = false;
  const btn = document.getElementById('genBtn');
  btn.className = 'btn btn-primary';
  btn.innerHTML = '\ud83c\udfa8 生成图片';
  btn.disabled = false;
  btn.onclick = startGenerate;
}

function openFolder() {
  fetch('/api/open-folder', { method: 'POST', headers: {'X-CSRF-Token': CSRF_TOKEN} }).catch(()=>{});
}

async function chooseFolder() {
  const btn = document.getElementById('chooseFolderBtn');
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '选择中...';
  try {
    const r = await fetch('/api/select-folder', {
      method: 'POST',
      headers: {'X-CSRF-Token': CSRF_TOKEN}
    });
    const d = await r.json();
    if (d.cancelled) {
      setStatus('已取消选择目录', 'info');
      return;
    }
    if (d.error) {
      setStatus('\u274c ' + d.error, 'err');
      return;
    }
    if (d.save_dir) {
      setSaveDir(d.save_dir);
      setStatus('\u2705 保存目录已更新', 'ok');
      await loadRecentImages();
    }
  } catch (e) {
    setStatus('\u274c 选择目录失败: ' + e.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
}

// Cmd+Enter 快捷生成
document.getElementById('prompt').addEventListener('keydown', function(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    if (!generating) startGenerate();
  }
});

// 页面加载后：恢复设置 + 加载历史图片
(async function initPage() {
  loadSettings();
  await loadServerSettings();
  checkEnv();
  await loadRecentImages();
})();
</script>
</body>
</html>"""

HTML_PAGE = HTML_PAGE.replace("__MAX__", str(MAX_IMAGES))
HTML_PAGE = HTML_PAGE.replace("__MAX_INPUT_IMAGES__", str(MAX_INPUT_IMAGES))


# ==================== 生成任务管理 ====================

class GenJob:
    """单次生成任务（可能包含多张并发图片）"""
    def __init__(self, job_id: str, prompt: str, size: str, quality: str, count: int,
                 api_key: str, url: str, save_dir: str,
                 input_images: Optional[List[Dict[str, str]]] = None):
        self.job_id = job_id
        self.prompt = prompt
        self.size = size
        self.quality = quality
        self.count = count
        self.api_key = api_key
        self.url = url
        self.save_dir = save_dir
        self.input_images = input_images or []

        self.images: List[Dict[str, Any]] = [{"done": False, "error": None, "url": None, "path": None}
                                              for _ in range(count)]
        self.completed = 0
        self.errors = 0
        self.done = False
        self.cancelled = False
        self.lock = threading.Lock()
        self._procs: Dict[int, subprocess.Popen] = {}
        self._proc_lock = threading.Lock()
        self._created = time.time()

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            action = "编辑中" if self.input_images else "生成中"
            status_text = f"{action}... {self.completed}/{self.count}"
            if self.cancelled:
                status_text = f"\u274c 已中断（完成 {self.completed} 张）"
            elif self.done:
                if self.errors == self.count:
                    status_text = f"\u274c 全部失败（{self.errors} 张）"
                else:
                    ok_count = self.completed - self.errors
                    extra = f"，失败 {self.errors}" if self.errors > 0 and self.errors < self.count else ""
                    status_text = f"完成 {ok_count} 张{extra}"
            return {
                "job_id": self.job_id,
                "done": self.done,
                "cancelled": self.cancelled,
                "total": self.count,
                "completed": self.completed,
                "errors": self.errors,
                "images": [{"done": img["done"], "error": img["error"], "url": img["url"]}
                           for img in self.images],
                "status_text": status_text,
            }

    def register_proc(self, idx: int, proc: subprocess.Popen):
        with self._proc_lock:
            self._procs[idx] = proc

    def unregister_proc(self, idx: int):
        with self._proc_lock:
            self._procs.pop(idx, None)

    def cancel_all_procs(self):
        with self._proc_lock:
            for idx, proc in list(self._procs.items()):
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass
        self.cancelled = True

    def mark_done(self, idx: int, path: Optional[str], error: Optional[str]):
        with self.lock:
            if idx < 0 or idx >= self.count:
                return
            self.images[idx]["done"] = True
            if error:
                self.images[idx]["error"] = error
                self.errors += 1
            else:
                self.images[idx]["url"] = GPTImageServer.file_url_for_path(path, self.save_dir) if path else None
                self.images[idx]["path"] = path
            self.completed += 1
            if self.completed >= self.count or self.cancelled:
                self.done = True


# ==================== Flask 应用 ====================

class GPTImageServer:
    @staticmethod
    def file_url_for_path(path: str, save_dir: str) -> Optional[str]:
        try:
            save_root = Path(save_dir).resolve()
            fpath = Path(path).resolve()
            rel = fpath.relative_to(save_root)
            return "/file/" + "/".join(rel.parts)
        except Exception:
            return None

    def __init__(self):
        self.api_key = os.environ.get(API_KEY_ENV, "")
        self.endpoint = os.environ.get(ENDPOINT_ENV, "").rstrip("/")
        self.save_dir = self._load_save_dir()
        Path(self.save_dir).mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, GenJob] = {}
        self._jobs_lock = threading.Lock()
        self._last_image_paths: List[str] = []
        self._csrf_token = uuid.uuid4().hex

    def _load_save_dir(self) -> str:
        try:
            if SETTINGS_PATH.exists():
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                path = str(data.get("save_dir") or "").strip()
                if path:
                    return str(Path(path).expanduser())
        except Exception as e:
            print(f"  [WARN] 读取设置失败: {e}")
        return DEFAULT_SAVE_DIR

    def _save_settings(self):
        try:
            SETTINGS_PATH.write_text(
                json.dumps({"save_dir": self.save_dir}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"  [WARN] 保存设置失败: {e}")

    def _set_save_dir(self, path: str):
        if not path or not str(path).strip():
            return "目录不能为空"
        save_dir = Path(str(path).strip()).expanduser()
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"无法创建目录: {e}"
        if not save_dir.is_dir():
            return "选择的路径不是文件夹"
        self.save_dir = str(save_dir.resolve())
        self._save_settings()
        return None

    # ---------- HTTP 路由 ----------
    def handle(self, method: str, path: str, body: Optional[bytes] = None,
               headers: Optional[Any] = None, upload_stream: Optional[Any] = None,
               content_length: int = 0):
        if method == "GET":
            if path == "/" or path == "/index.html":
                return self._serve_html()
            elif path == "/api/status":
                return self._json_response(self._api_status())
            elif path == "/api/settings":
                return self._json_response(self._api_settings())
            elif path == "/api/images":
                return self._json_response(self._api_list_images())
            elif path.startswith("/api/job/") and path.endswith("/cancel") is False and "/api/job/" in path:
                return self._json_response(self._api_job_status(path))
            elif path.startswith("/file/"):
                return self._serve_file(path)
            else:
                return self._not_found()
        elif method == "POST":
            if not self._is_trusted_post(headers):
                return self._json_response({"error": "请求来源无效，请刷新页面后重试"})
            if path == "/api/generate":
                if upload_stream is not None:
                    return self._json_response(self._api_generate_multipart(headers, upload_stream, content_length))
                return self._json_response(self._api_generate(body))
            elif path == "/api/select-folder":
                return self._json_response(self._api_select_folder())
            elif path == "/api/open-folder":
                return self._json_response(self._open_folder())
            elif path.startswith("/api/job/") and path.endswith("/cancel"):
                return self._json_response(self._api_job_cancel(path))
            else:
                return self._not_found()
        return self._not_found()

    # ---------- 页面 / 文件 ----------
    def _serve_html(self):
        page = HTML_PAGE.replace("__CSRF_TOKEN__", self._csrf_token)
        page = page.replace("SAVE_DIR_PLACEHOLDER", self.save_dir)
        return "200 OK", "text/html; charset=utf-8", page.encode("utf-8")

    def _serve_file(self, path: str):
        rel_name = unquote(path[len("/file/"):]).lstrip("/")  # 二次解码防御
        # 安全校验：只允许当前保存目录下的文件
        save_dir = Path(self.save_dir).resolve()
        fpath = (save_dir / rel_name).resolve()
        try:
            if not str(fpath).startswith(str(save_dir) + os.sep):
                return "403 Forbidden", "text/plain", b"forbidden"
            if not fpath.exists():
                print(f"  [WARN] 文件不存在: {fpath} (请求: {path})")
                return "404 Not Found", "text/plain", b"not found"
            data = fpath.read_bytes()
            return "200 OK", "image/png", data
        except Exception as e:
            print(f"  [ERROR] 读取文件失败: {e}")
            return "500 Error", "text/plain", str(e).encode("utf-8")

    # ---------- API ----------
    def _is_trusted_post(self, headers: Optional[Any]) -> bool:
        if headers is None:
            return False
        token = headers.get("X-CSRF-Token", "")
        if token != self._csrf_token:
            return False
        origin = headers.get("Origin")
        if not origin:
            return True
        return origin in {
            f"http://127.0.0.1:{PORT}",
            f"http://localhost:{PORT}",
        }

    def _api_status(self):
        if not self.api_key:
            return {"api_ready": False, "message": "未检测到 OPENAI_API_KEY"}
        if not self.endpoint:
            return {"api_ready": False, "message": "未检测到 AZURE_OPENAI_IMAGE_ENDPOINT"}
        domain = self.endpoint.split("//")[-1].split("/")[0]
        return {"api_ready": True, "endpoint_domain": domain}

    def _api_settings(self):
        return {"save_dir": self.save_dir}

    def _api_list_images(self):
        """返回当前保存目录下的历史图片列表与文件树。"""
        try:
            save_dir = Path(self.save_dir)
            if not save_dir.exists():
                return {"images": [], "tree": self._build_image_tree([]), "total": 0}
            files = []
            image_paths = [p for p in save_dir.rglob("*.png") if p.is_file()]
            for f in sorted(image_paths, key=lambda p: p.stat().st_mtime, reverse=True):
                if not f.is_file() or f.suffix.lower() != ".png":
                    continue
                try:
                    stat = f.stat()
                    size_kb = f.stat().st_size / 1024
                    rel = f.relative_to(save_dir)
                    rel_str = "/".join(rel.parts)
                    folder = "/".join(rel.parts[:-1])
                    files.append({
                        "done": True,
                        "url": "/file/" + rel_str,
                        "path": str(f),
                        "name": f.name,
                        "rel": rel_str,
                        "folder": folder,
                        "mtime": stat.st_mtime,
                        "size_kb": round(size_kb, 1),
                    })
                except OSError:
                    continue
            return {"images": files, "tree": self._build_image_tree(files), "total": len(files)}
        except Exception as e:
            return {"images": [], "tree": self._build_image_tree([]), "error": str(e)}

    def _build_image_tree(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        tree = {
            "id": "__all__",
            "type": "folder",
            "name": "全部历史",
            "folder": "__all__",
            "count": len(images),
            "children": [],
        }
        root_images = [img for img in images if not img.get("folder")]
        if root_images:
            tree["children"].append({
                "id": "folder:",
                "type": "folder",
                "name": "根目录",
                "folder": "",
                "count": len(root_images),
                "children": [self._image_tree_file(img) for img in sorted(root_images, key=lambda x: x.get("mtime", 0), reverse=True)],
            })

        folder_nodes: Dict[str, Dict[str, Any]] = {}
        top_nodes: List[Dict[str, Any]] = []

        def ensure_folder(folder: str) -> Dict[str, Any]:
            if folder in folder_nodes:
                return folder_nodes[folder]
            parts = folder.split("/") if folder else []
            node = {
                "id": "folder:" + folder,
                "type": "folder",
                "name": parts[-1] if parts else "根目录",
                "folder": folder,
                "count": 0,
                "children": [],
            }
            folder_nodes[folder] = node
            parent = "/".join(parts[:-1])
            if parent:
                ensure_folder(parent)["children"].append(node)
            else:
                top_nodes.append(node)
            return node

        for img in images:
            folder = img.get("folder") or ""
            if not folder:
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                ensure_folder("/".join(parts[:i]))["count"] += 1
            ensure_folder(folder)["children"].append(self._image_tree_file(img))

        def sort_children(node: Dict[str, Any]):
            children = node.get("children", [])
            children.sort(key=lambda item: (
                0 if item.get("type") == "folder" else 1,
                -float(item.get("mtime", 0)) if item.get("type") == "file" else 0,
                str(item.get("name", "")).lower()
            ))
            for child in children:
                if child.get("type") == "folder":
                    sort_children(child)

        top_nodes.sort(key=lambda item: str(item.get("name", "")).lower(), reverse=True)
        tree["children"].extend(top_nodes)
        sort_children(tree)
        return tree

    def _image_tree_file(self, img: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": "file:" + str(img.get("rel", "")),
            "type": "file",
            "name": img.get("name", ""),
            "rel": img.get("rel", ""),
            "url": img.get("url", ""),
            "mtime": img.get("mtime", 0),
            "size_kb": img.get("size_kb", 0),
        }

    def _open_folder(self):
        Path(self.save_dir).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", self.save_dir])
        except Exception:
            pass
        return {"success": True}

    def _api_select_folder(self):
        script = (
            'POSIX path of (choose folder with prompt '
            '"选择图片保存目录" default location POSIX file '
            + json.dumps(self.save_dir)
            + ')'
        )
        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=300
            )
        except subprocess.TimeoutExpired:
            return {"error": "选择目录超时"}
        except Exception as e:
            return {"error": f"无法打开目录选择器: {e}"}
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            if "User canceled" in err or proc.returncode == 1:
                return {"cancelled": True, "save_dir": self.save_dir}
            return {"error": err or "目录选择失败"}
        selected = proc.stdout.strip()
        if selected.endswith(os.sep) and len(selected) > 1:
            selected = selected.rstrip(os.sep)
        error = self._set_save_dir(selected)
        if error:
            return {"error": error, "save_dir": self.save_dir}
        return {"success": True, "save_dir": self.save_dir}

    def _build_image_url(self, action: str) -> str:
        """构造 images/generations 或 images/edits 地址。"""
        raw_endpoint = self.endpoint.rstrip("/")
        action_path = f"/images/{action}"
        if "/openai/deployments/" in raw_endpoint:
            base = raw_endpoint.split("?", 1)[0].rstrip("/")
            if base.endswith("/images/generations") or base.endswith("/images/edits"):
                base = base.rsplit("/images/", 1)[0] + action_path
            elif base.endswith("/images"):
                base = base + f"/{action}"
            elif "/images/" not in base:
                base = base + action_path
            return f"{base}?api-version={API_VERSION}"

        if raw_endpoint.endswith("/openai"):
            raw_endpoint = raw_endpoint[:-7]
        return f"{raw_endpoint}/openai/deployments/{DEPLOYMENT}{action_path}?api-version={API_VERSION}"

    def _auth_curl_headers(self, url: str) -> List[str]:
        host = urlparse(url).netloc.lower()
        if "openai.azure.com" in host or "cognitiveservices.azure.com" in host:
            return ["-H", f"api-key: {self.api_key}"]
        return ["-H", f"Authorization: Bearer {self.api_key}"]

    def _decode_input_images(self, raw_images: Any):
        if not raw_images:
            return [], None
        if not isinstance(raw_images, list):
            return [], "输入图片格式不正确"
        if len(raw_images) > MAX_INPUT_IMAGES:
            raw_images = raw_images[:MAX_INPUT_IMAGES]

        decoded = []
        try:
            for i, item in enumerate(raw_images):
                if not isinstance(item, dict):
                    return decoded, f"第 {i + 1} 张输入图片格式不正确"
                name = str(item.get("name") or f"input_{i + 1}.png")
                mime = str(item.get("mime") or "").lower()
                data = str(item.get("data") or "")
                if "," in data and data.startswith("data:"):
                    header, data = data.split(",", 1)
                    if not mime and ";" in header:
                        mime = header[5:].split(";", 1)[0].lower()
                if mime not in ("image/png", "image/jpeg", "image/jpg"):
                    return decoded, "输入图片只支持 PNG 或 JPG"
                try:
                    img_bytes = base64.b64decode(data, validate=True)
                except Exception:
                    try:
                        img_bytes = base64.b64decode(data + "=" * ((4 - len(data) % 4) % 4))
                    except Exception:
                        return decoded, f"第 {i + 1} 张输入图片 base64 解码失败"
                if not img_bytes:
                    return decoded, f"第 {i + 1} 张输入图片为空"
                if len(img_bytes) > MAX_INPUT_IMAGE_BYTES:
                    return decoded, "单张输入图片不能超过 50MB"

                suffix = ".jpg" if mime in ("image/jpeg", "image/jpg") else ".png"
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="gptimg_input_")
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(img_bytes)
                decoded.append({"path": tmp_path, "name": name, "mime": "image/jpeg" if suffix == ".jpg" else "image/png"})
            return decoded, None
        except Exception as e:
            return decoded, f"读取输入图片失败: {e}"

    def _cleanup_input_images(self, input_images: List[Dict[str, str]]):
        for item in input_images:
            path = item.get("path")
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass

    def _form_value(self, form: cgi.FieldStorage, name: str, default: str = "") -> str:
        if name not in form:
            return default
        item = form[name]
        if isinstance(item, list):
            item = item[0] if item else None
        if item is None or getattr(item, "filename", None):
            return default
        value = item.value
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        return str(value)

    def _decode_uploaded_images(self, form: cgi.FieldStorage):
        if "input_images" not in form:
            return [], None
        fields = form["input_images"]
        if not isinstance(fields, list):
            fields = [fields]
        fields = [field for field in fields if getattr(field, "filename", None)]
        if len(fields) > MAX_INPUT_IMAGES:
            return [], f"一次最多上传 {MAX_INPUT_IMAGES} 张输入图片"

        decoded = []
        try:
            for i, field in enumerate(fields):
                filename = os.path.basename(field.filename or f"input_{i + 1}.png")
                mime = (getattr(field, "type", None) or mimetypes.guess_type(filename)[0] or "").lower()
                if mime not in ("image/png", "image/jpeg", "image/jpg"):
                    return decoded, "输入图片只支持 PNG 或 JPG"
                suffix = ".jpg" if mime in ("image/jpeg", "image/jpg") else ".png"
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="gptimg_input_")
                total = 0
                try:
                    with os.fdopen(tmp_fd, "wb") as out:
                        while True:
                            chunk = field.file.read(1024 * 1024)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > MAX_INPUT_IMAGE_BYTES:
                                try:
                                    os.unlink(tmp_path)
                                except Exception:
                                    pass
                                return decoded, "单张输入图片不能超过 50MB"
                            out.write(chunk)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    raise
                if total == 0:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
                    return decoded, f"第 {i + 1} 张输入图片为空"
                decoded.append({"path": tmp_path, "name": filename, "mime": "image/jpeg" if suffix == ".jpg" else "image/png"})
            return decoded, None
        except Exception as e:
            return decoded, f"读取输入图片失败: {e}"

    def _api_generate(self, body: Optional[bytes]):
        if not body:
            return {"error": "请求体为空"}
        if len(body) > MAX_JSON_BODY_BYTES:
            return {"error": "JSON 请求体过大，请刷新页面后重试"}
        try:
            req = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": "JSON 解析失败"}

        input_images, input_error = self._decode_input_images(req.get("input_images"))
        if input_error:
            self._cleanup_input_images(input_images)
            return {"error": input_error}
        return self._start_generation(req, input_images)

    def _api_generate_multipart(self, headers: Any, stream: Any, content_length: int):
        if content_length <= 0:
            return {"error": "请求体为空"}
        if content_length > MAX_UPLOAD_BODY_BYTES:
            return {"error": "上传内容过大，请减少图片数量或压缩图片"}

        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(content_length),
        }
        try:
            form = cgi.FieldStorage(fp=stream, headers=headers, environ=environ, keep_blank_values=True)
        except Exception as e:
            return {"error": f"表单解析失败: {e}"}

        input_images, input_error = self._decode_uploaded_images(form)
        if input_error:
            self._cleanup_input_images(input_images)
            return {"error": input_error}

        req = {
            "prompt": self._form_value(form, "prompt"),
            "ratio": self._form_value(form, "ratio", "1:1"),
            "quality": self._form_value(form, "quality", "medium"),
            "count": self._form_value(form, "count", "1"),
        }
        return self._start_generation(req, input_images)

    def _start_generation(self, req: Dict[str, Any], input_images: List[Dict[str, str]]):
        prompt = str(req.get("prompt", "")).strip()
        if not prompt:
            self._cleanup_input_images(input_images)
            return {"error": "提示词不能为空"}

        if not self.api_key:
            self._cleanup_input_images(input_images)
            return {"error": "未配置 OPENAI_API_KEY 环境变量"}
        if not self.endpoint:
            self._cleanup_input_images(input_images)
            return {"error": "未配置 AZURE_OPENAI_IMAGE_ENDPOINT 环境变量"}

        # 参数处理
        ratio = req.get("ratio", "1:1")
        size = RATIO_TO_SIZE.get(ratio, "1024x1024")
        quality = req.get("quality", "medium")
        if quality not in ("low", "medium", "high"):
            quality = "medium"
        try:
            count = int(req.get("count", 1))
        except (ValueError, TypeError):
            count = 1
        count = max(1, min(count, MAX_IMAGES))

        # 构造 URL：有输入图时走 edits，否则走 generations
        is_edit = len(input_images) > 0
        url = self._build_image_url("edits" if is_edit else "generations")

        # 创建任务
        job_id = uuid.uuid4().hex[:12]
        job = GenJob(job_id=job_id, prompt=prompt, size=size, quality=quality,
                     count=count, api_key=self.api_key, url=url,
                     save_dir=self.save_dir, input_images=input_images)
        with self._jobs_lock:
            self._jobs[job_id] = job
        # 清理老任务（只保留最近 20 个）
        with self._jobs_lock:
            if len(self._jobs) > 20:
                sorted_ids = sorted(self._jobs.keys(),
                                     key=lambda jid: getattr(self._jobs[jid], '_created', 0))
                for old_id in sorted_ids[:-20]:
                    self._jobs.pop(old_id, None)

        mode = "图片编辑" if is_edit else "文生图"
        print(f"\n[任务 {job_id}] 启动: {mode} | {count} 张 | {size} | quality={quality}")
        if is_edit:
            print(f"  输入图片: {len(input_images)} 张")
        print(f"  prompt: {prompt[:80]}")

        # 后台线程：并发启动每个图片的子任务
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

        return {"success": True, "job_id": job_id, "count": count}

    def _api_job_status(self, path: str):
        job_id = path[len("/api/job/"):]
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job:
            return {"error": "任务不存在或已过期"}
        return job.get_status()

    def _api_job_cancel(self, path: str):
        job_id = path[len("/api/job/"):-len("/cancel")]
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if not job:
            return {"error": "任务不存在"}
        job.cancel_all_procs()
        job.done = True
        print(f"[任务 {job_id}] 用户已中断")
        return {"success": True}

    # ---------- 后台执行 ----------
    def _run_job(self, job: GenJob):
        """主任务线程：用信号量限制并发，逐个启动子线程"""
        try:
            sem = threading.Semaphore(MAX_CONCURRENT)
            threads = []
            for i in range(job.count):
                t = threading.Thread(target=self._generate_one, args=(job, i, sem), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

            with job.lock:
                job.done = True
            print(f"[任务 {job.job_id}] 全部结束 完成={job.completed} 失败={job.errors}"
                  f" 已取消={'是' if job.cancelled else '否'}")
        finally:
            self._cleanup_input_images(job.input_images)

    def _generate_one(self, job: GenJob, idx: int, sem: threading.Semaphore):
        """生成单张图片的子线程"""
        if job.cancelled:
            job.mark_done(idx, None, "已取消")
            return
        with sem:
            if job.cancelled:
                job.mark_done(idx, None, "已取消")
                return
            try:
                img_bytes = self._call_api(job, idx)
                if img_bytes is None:
                    return  # 错误信息已在 _call_api 中处理
                path = self._save_image(img_bytes, job.prompt, idx, job.count)
                job.mark_done(idx, path, None)
                print(f"  [任务 {job.job_id} #{idx+1}] 已保存: {os.path.basename(path)}")
            except Exception as e:
                print(f"  [任务 {job.job_id} #{idx+1}] 异常: {e}")
                job.mark_done(idx, None, str(e)[:80])

    def _call_api(self, job: GenJob, idx: int) -> Optional[bytes]:
        """调用 Azure GPT-Image-2 生成/编辑单张图片；返回图片二进制数据或 None"""
        if job.cancelled:
            job.mark_done(idx, None, "已取消")
            return None

        is_edit = len(job.input_images) > 0

        # 不做 429 重试：触发速率限制就直接展示错误
        if job.cancelled:
            job.mark_done(idx, None, "已取消")
            return None

        tmp_path = None
        raw_json = ""
        err_msg = ""
        http_code = 0
        t0 = time.time()
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix=f"gptimg_{job.job_id}_{idx}_")
            os.close(tmp_fd)

            base_curl = [
                "curl", "-4", "-sS", "-k",
                "-X", "POST", job.url,
                *self._auth_curl_headers(job.url),
                "--max-time", "600",
                "--connect-timeout", "30",
                "--retry", "3",
                "--retry-delay", "2",
                "-w", "%{stderr}DNS=%{time_namelookup}s | CONNECT=%{time_connect}s | TLS=%{time_appconnect}s | TTFB=%{time_starttransfer}s | TOTAL=%{time_total}s | HTTP=%{http_code} | SIZE=%{size_download}B",
                "-o", tmp_path,
            ]
            if is_edit:
                curl_cmd = base_curl + [
                    "--form-string", f"prompt={job.prompt}",
                    "--form-string", f"size={job.size}",
                    "--form-string", f"quality={job.quality}",
                    "--form-string", "output_compression=100",
                    "--form-string", "output_format=png",
                    "--form-string", "n=1",
                ]
                for input_image in job.input_images:
                    image_path = input_image["path"]
                    image_mime = input_image.get("mime") or mimetypes.guess_type(image_path)[0] or "image/png"
                    curl_cmd += ["-F", f"image[]=@{image_path};type={image_mime}"]
            else:
                payload = {
                    "prompt": job.prompt,
                    "size": job.size,
                    "quality": job.quality,
                    "output_compression": 100,
                    "output_format": "png",
                    "n": 1,
                }
                curl_cmd = base_curl + [
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                ]
            action = "编辑" if is_edit else "生成"
            print(f"  [任务 {job.job_id} #{idx+1}] 发起{action}请求 ({job.size}, q={job.quality})")
            proc = subprocess.Popen(curl_cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, text=True)
            job.register_proc(idx, proc)
            try:
                _, stderr = proc.communicate(timeout=610)
            except subprocess.TimeoutExpired:
                proc.kill()
                job.unregister_proc(idx)
                err_msg = "请求超时（600s）"
                stderr = ""
            else:
                job.unregister_proc(idx)

            # 解析 stderr：分离 curl 错误文本 与 -w 输出的时间/状态码行
            err_lines = []
            timing_line = None
            if stderr:
                for ln in stderr.strip().splitlines():
                    ln = ln.strip()
                    if "DNS=" in ln and "HTTP=" in ln:
                        timing_line = ln
                        for part in ln.split("|"):
                            part = part.strip()
                            if part.startswith("HTTP="):
                                try:
                                    http_code = int(part.split("=", 1)[1])
                                except (ValueError, IndexError):
                                    pass
                    elif ln and not ln.startswith("DNS="):
                        err_lines.append(ln)

            if timing_line:
                print(f"  [任务 {job.job_id} #{idx+1}] ⏱  {timing_line}")

            if proc.returncode != 0:
                if err_lines:
                    err_msg = " ".join(err_lines)
                else:
                    err_msg = f"curl 失败（退出码 {proc.returncode}）"
            else:
                try:
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        raw_json = f.read()
                except Exception as e:
                    err_msg = f"读取响应失败: {e}"
        except Exception as e:
            err_msg = str(e)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        dt = time.time() - t0

        if job.cancelled:
            job.mark_done(idx, None, "已取消")
            return None

        # 网络层失败（curl 非 0）
        if not raw_json and err_msg:
            print(f"  [任务 {job.job_id} #{idx+1}] 网络失败 ({dt:.1f}s): {err_msg}")
            job.mark_done(idx, None, err_msg[:120])
            return None

        # 解析 JSON
        try:
            result = json.loads(raw_json)
        except json.JSONDecodeError:
            preview = raw_json[:200]
            print(f"  [任务 {job.job_id} #{idx+1}] JSON 解析失败: {preview}")
            job.mark_done(idx, None, "API 响应格式异常")
            return None

        # HTTP 429：不重试，直接展示错误给用户
        if http_code == 429:
            api_err = result.get("error") if isinstance(result, dict) else None
            api_msg = ""
            if isinstance(api_err, dict):
                api_msg = api_err.get("message") or ""
            elif isinstance(api_err, str):
                api_msg = api_err
            if not api_msg:
                api_msg = "请求过于频繁，已超出 Azure 速率限制"
            print(f"  [任务 {job.job_id} #{idx+1}] HTTP 429 ({dt:.1f}s): {api_msg[:100]}")
            job.mark_done(idx, None, f"超出速率限制（HTTP 429）：{api_msg[:120]}")
            return None

        # HTTP 4xx/5xx（非 429）：直接展示错误，不重试
        if http_code >= 400:
            api_err = result.get("error") if isinstance(result, dict) else None
            api_msg = ""
            if isinstance(api_err, dict):
                api_msg = api_err.get("message") or api_err.get("code") or ""
            elif isinstance(api_err, str):
                api_msg = api_err
            if not api_msg:
                api_msg = str(result)[:200] if isinstance(result, dict) else raw_json[:200]
            print(f"  [任务 {job.job_id} #{idx+1}] API 拒绝 ({dt:.1f}s, HTTP {http_code}): {api_msg[:120]}")
            job.mark_done(idx, None, f"API 拒绝（HTTP {http_code}）：{api_msg[:120]}")
            return None

        # 正常响应（HTTP 2xx）
        data_list = result.get("data", []) if isinstance(result, dict) else []
        if not data_list:
            api_err = result.get("error") if isinstance(result, dict) else None
            api_msg = ""
            if isinstance(api_err, dict):
                api_msg = api_err.get("message") or ""
            msg = api_msg or "API 未返回图片数据"
            print(f"  [任务 {job.job_id} #{idx+1}] 无图片数据 ({dt:.1f}s): {msg}")
            job.mark_done(idx, None, msg[:120])
            return None

        print(f"  [任务 {job.job_id} #{idx+1}] 成功 ({dt:.1f}s)")

        # 提取图片（到这里 data_list 已确认非空）
        item = data_list[0]
        if "b64_json" in item:
            raw_b64 = item["b64_json"]
            if "%" in raw_b64:
                raw_b64 = unquote(raw_b64)
            try:
                return base64.b64decode(raw_b64)
            except Exception:
                raw_b64 += "=" * (4 - len(raw_b64) % 4)
                try:
                    return base64.b64decode(raw_b64)
                except Exception as e:
                    job.mark_done(idx, None, f"base64 解码失败: {e}")
                    return None
        elif "url" in item:
            # 下载图片 URL
            img_url = item["url"]
            tmp_img = None
            try:
                tmp_fd, tmp_img = tempfile.mkstemp(suffix=".png", prefix="gptimg_dl_")
                os.close(tmp_fd)
                proc = subprocess.run(
                    ["curl", "-4", "-sSL", img_url, "--max-time", "90", "-o", tmp_img],
                    timeout=100, capture_output=True
                )
                if proc.returncode == 0:
                    with open(tmp_img, "rb") as f:
                        return f.read()
                job.mark_done(idx, None, "图片下载失败")
                return None
            except Exception as e:
                job.mark_done(idx, None, f"下载失败: {e}")
                return None
            finally:
                if tmp_img and os.path.exists(tmp_img):
                    try:
                        os.unlink(tmp_img)
                    except Exception:
                        pass
        else:
            job.mark_done(idx, None, "响应格式不支持")
            return None

    def _save_image(self, img_bytes: bytes, prompt: str, idx: int, total: int) -> str:
        save_dir = Path(self.save_dir) / datetime.now().strftime("%Y-%m-%d")
        save_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in prompt)[:40].strip().replace(" ", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if total > 1:
            name = f"{ts}_{safe}_{idx+1:02d}.png"
        else:
            name = f"{ts}_{safe}.png"
        fpath = save_dir / name
        fpath.write_bytes(img_bytes)
        return str(fpath)

    def _json_response(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return "200 OK", "application/json; charset=utf-8", body

    def _not_found(self):
        return "404 Not Found", "text/plain", b"Not Found"


# ==================== HTTP 服务器 ====================

from http.server import HTTPServer, BaseHTTPRequestHandler


class RequestHandler(BaseHTTPRequestHandler):
    server_app: GPTImageServer = None  # type: ignore

    def do_GET(self):
        # 忽略 query string，并 URL 解码（中文文件名会被浏览器编码为 %XX）
        path = unquote(self.path.split('?')[0])
        self._respond("GET", path)

    def do_POST(self):
        path = unquote(self.path.split('?')[0])
        content_length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "").lower()
        if path == "/api/generate" and content_type.startswith("multipart/form-data"):
            self._respond("POST", path, None, upload_stream=self.rfile, content_length=content_length)
            return
        if content_length > MAX_JSON_BODY_BYTES:
            self.close_connection = True
            body = json.dumps({"error": "请求体过大，请刷新页面后重试"}, ensure_ascii=False).encode("utf-8")
            self._send_raw("200 OK", "application/json; charset=utf-8", body)
            return
        body = self.rfile.read(content_length) if content_length > 0 else None
        self._respond("POST", path, body, content_length=content_length)

    def _respond(self, method: str, path: str, body: Optional[bytes] = None,
                 upload_stream: Optional[Any] = None, content_length: int = 0):
        status, content_type, data = self.server_app.handle(
            method, path, body, headers=self.headers,
            upload_stream=upload_stream, content_length=content_length
        )
        self._send_raw(status, content_type, data)

    def _send_raw(self, status: str, content_type: str, data: bytes):
        self.send_response(int(status.split()[0]))
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # 静默日志


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print("  GPT-Image-2 图片生成器 (Web 版)")
    print("=" * 50)

    app = GPTImageServer()

    if app.api_key and app.endpoint:
        domain = app.endpoint.split("//")[-1].split("/")[0]
        print(f"  ✅ API 已就绪 ({domain})")
        print(f"  📍 Endpoint: {app.endpoint}")
    else:
        print("  ⚠️  环境变量未配置，请检查:")
        print(f"     export OPENAI_API_KEY=...")
        print(f"     export AZURE_OPENAI_IMAGE_ENDPOINT=...")

    print(f"  📁 图片保存至: {app.save_dir}")
    print(f"  🌐 浏览器即将打开...")

    server = HTTPServer(("127.0.0.1", PORT), RequestHandler)
    RequestHandler.server_app = app

    def open_browser():
        import time
        time.sleep(0.5)
        webbrowser.open(f"http://127.0.0.1:{PORT}")

    threading.Thread(target=open_browser, daemon=True).start()

    print(f"  🟢 服务运行中: http://127.0.0.1:{PORT}")
    print(f"  多图并发上限: {MAX_CONCURRENT} | 单次最多: {MAX_IMAGES} 张")
    print("  (关闭此窗口即可停止服务)")
    print("=" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
        server.shutdown()


if __name__ == "__main__":
    main()

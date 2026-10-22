#!/usr/bin/env python3
"""
OmniBond - Embedded Web Studio UI HTML/CSS/JS Frontend Template.
"""

from __future__ import annotations

# =====================================================================
# 7. WEB STUDIO UI (127.0.0.1:8085) - WITH PER-APP GRAPHS, FILTERS & FOCUS
# =====================================================================

WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmniBond</title>
<style>
  :root {
    --bg: #09090b;
    --panel: #0c0c0f;
    --card-hover: #121217;
    --hairline: #1e1e24;
    --text: #fafafa;
    --muted: #a1a1aa;
    --dim: #52525b;
    --amber: #f59e0b;
    --emerald: #10b981;
    --cyan: #38bdf8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--hairline);
    color: var(--text);
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  @keyframes topbarGreenFlow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  .topbar {
    background: var(--panel);
    padding: 13px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    transition: background 0.3s ease;
  }
  .topbar.bonding-active {
    background: linear-gradient(110deg, #0c0c0f 0%, #062b1f 25%, #0e523a 50%, #062b1f 75%, #0c0c0f 100%);
    background-size: 260% 260%;
    animation: topbarGreenFlow 5s ease infinite;
  }
  .brand-row { display: flex; align-items: center; gap: 12px; }
  .ob-badge {
    background: var(--amber);
    color: #09090b;
    font-weight: 900;
    font-size: 12px;
    padding: 4px 7px;
  }
  .brand-title { font-size: 16px; font-weight: 800; }
  .brand-sub {
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  .top-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

  .btn {
    background-color: #14141b;
    color: var(--text);
    border: 1px solid #272732;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease, transform 0.14s ease;
    position: relative;
  }
  .btn:hover { background-color: #252536; color: #ffffff; border-color: #272732; transform: translateY(-1px); }
  .btn.primary { background-color: #fafafa; color: #09090b; border-color: #fafafa; }
  .btn.primary:hover { background-color: #f59e0b; color: #09090b; border-color: #f59e0b; }
  .btn.amber { background-color: #f59e0b; color: #09090b; border-color: #f59e0b; }
  .btn.amber:hover { background-color: #fbbf24; color: #09090b; border-color: #fbbf24; }
  .btn.active { background-color: #1c1912; color: var(--amber); border-color: #3a301a; }
  .btn.active:hover { background-color: #292315; color: #fbbf24; border-color: #3a301a; }

  .workspace-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.18fr);
    gap: 1px;
    background: var(--hairline);
    flex: 1;
    min-height: 0;
  }
  @media (max-width: 1100px) { .workspace-grid { grid-template-columns: 1fr; } }

  .section-container {
    background: var(--panel);
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .section-head {
    padding: 13px 18px 11px 18px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }
  .kicker {
    font-family: 'Consolas', monospace;
    font-size: 10.5px;
    font-weight: 700;
    color: var(--amber);
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  .section-title { font-size: 16px; font-weight: 800; margin-top: 2px; }

  /* Fixed Issues 2 & 8: Use var(--panel) background with explicit right & bottom borders on cards
     so adapter cards have their right outline, program/service cards have their bottom outline,
     and unoccupied grid cells never show a lighter hairline hue. */
  .bento-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
    gap: 0;
    background: var(--panel);
    border-bottom: 1px solid var(--hairline);
  }
  .adapter-scroll {
    width: 100%;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    background: var(--panel);
    scrollbar-color: #3f3f46 #0c0c0f;
  }
  #adapterBentoGrid {
    display: flex;
    width: max-content;
    min-width: 100%;
    background: var(--panel);
    border-bottom: 1px solid var(--hairline);
  }
  #adapterBentoGrid .bento-card {
    flex: 0 0 280px;
    border-right: 1px solid var(--hairline);
    border-bottom: 1px solid var(--hairline);
  }
  .app-grid-scroll {
    min-height: 240px;
    max-height: min(58vh, 680px);
    overflow: auto;
    overscroll-behavior: contain;
    background: var(--panel);
    scrollbar-color: #3f3f46 #0c0c0f;
  }
  #appBentoGrid {
    background: var(--panel);
    border-bottom: 0;
  }
  #appBentoGrid.list-view {
    display: flex;
    flex-direction: column;
    gap: 0;
    background: var(--panel);
  }
  #appBentoGrid.list-view .bento-card {
    width: 100%;
    min-height: 0;
    flex-direction: column;
    gap: 10px;
  }
  #appBentoGrid.list-view .bento-card > div:first-child { width: 100%; min-width: 0; }
  #appBentoGrid.list-view .card-actions { flex: 0 0 auto; align-self: stretch; width: 100%; }
  #appBentoGrid.list-view .card-select-wrap { width: 100%; }
  #appBentoGrid.list-view .sparkline-box { width: 100%; max-width: none; }
  .app-card-controls { display:flex; flex:0 0 auto; gap:5px; align-items:center; justify-content:flex-end; flex-wrap:nowrap; }
  .bento-card {
    background: var(--panel);
    border-right: 1px solid var(--hairline);
    border-bottom: 1px solid var(--hairline);
    padding: 16px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 208px;
    min-width: 0;
    overflow: hidden;
    transition: background 0.15s;
  }
  .bento-card:hover { background: var(--card-hover); }
  .card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }
  .num-badge {
    font-family: 'Consolas', monospace;
    font-size: 11px;
    font-weight: 800;
    color: #09090b;
    padding: 2px 6px;
    flex-shrink: 0;
  }
  .card-meta-links {
    font-family: 'Consolas', monospace;
    font-size: 10px;
    color: var(--muted);
  }
  .focus-link, .favorite-btn, .app-card-controls .card-btn {
    box-sizing: border-box;
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    justify-content: center;
    height: 26px;
    padding: 0 6px;
    white-space: nowrap;
    font-family: 'Consolas', monospace;
    font-size: 9px;
    font-weight: 800;
    line-height: 1;
    cursor: pointer;
  }
  .favorite-btn {
    width: 28px;
    padding: 0;
    font-size: 13px;
  }
  .focus-link, .app-card-controls .card-btn {
    width: 72px;
    color: var(--text);
    background: #121218;
    border: 1px solid #30303b;
    text-transform: uppercase;
  }
  .focus-link:hover, .app-card-controls .card-btn:hover, .favorite-btn:hover {
    background-color: #252536;
    color: #ffffff;
    border-color: #30303b;
  }
  .favorite-btn {
    color: var(--text);
    background: #121218;
    border: 1px solid #30303b;
    transition: background-color 0.14s ease, color 0.14s ease;
  }
  .favorite-btn.active { background-color: #1f1b12; color: var(--amber); border-color: #30303b; }
  .favorite-btn.active:hover { background-color: #2b2416; color: #fbbf24; border-color: #30303b; }

  /* Issue 5: Safe space & clean truncation for application names inside card containers */
  .card-identity {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    min-width: 0;
    width: 100%;
    padding-right: 4px;
  }
  .card-icon {
    width: 34px;
    height: 34px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 12px;
    color: #fff;
    flex-shrink: 0;
  }
  .card-identity-text {
    min-width: 0;
    flex: 1;
    overflow: hidden;
    padding-right: 4px;
  }
  .card-name {
    font-size: 13.5px;
    font-weight: 800;
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
    width: 100%;
  }
  .card-title-main {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
    flex: 0 1 auto;
  }
  .card-title-ext {
    font-family: 'Consolas', monospace;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    background: #14141d;
    flex-shrink: 0;
    max-width: 110px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .card-desc {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: block;
  }

  .status-box {
    display: inline-block;
    font-family: 'Consolas', monospace;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    background: rgba(16, 185, 129, 0.08);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    margin-bottom: 6px;
  }
  .status-box.pinned {
    background: rgba(56, 189, 248, 0.1);
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.4);
  }
  .status-box.quota-reached {
    background:rgba(239,68,68,.1);
    color:#f87171;
    border-color:rgba(239,68,68,.4);
  }

  .sparkline-box {
    background: #07070a;
    border: 1px solid #181820;
    padding: 6px 8px;
    margin-bottom: 11px;
  }
  .sparkline-head {
    display: flex;
    justify-content: space-between;
    font-family: 'Consolas', monospace;
    font-size: 9.5px;
    color: var(--muted);
    margin-bottom: 2px;
  }
  canvas.app-spark { width: 100%; height: 32px; display: block; }

  .card-actions { display: flex; gap: 6px; margin-top: auto; min-width: 0; }
  .card-btn, .card-select {
    flex: 1;
    background-color: #09090d;
    color: var(--text);
    border: 1px solid #272732;
    padding: 6px 8px;
    font-size: 10.5px;
    font-weight: 800;
    text-transform: uppercase;
    cursor: pointer;
  }
  .card-btn:hover, .styled-select-trigger:hover { border-color: #272732; background-color: #242434; color: #ffffff; }
  .styled-select-wrap {
    position:relative;
    display:inline-flex;
    flex:1 1 auto;
    min-width:0;
    vertical-align:middle;
  }
  .styled-select-trigger {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    min-width:0;
    width:100%;
    height:31px;
    padding:5px 9px;
    overflow:hidden;
    color:var(--text);
    background-color:#14141b;
    border:1px solid #272732;
    border-radius:0;
    font:700 10px 'Segoe UI',system-ui,sans-serif;
    text-align:left;
    cursor:pointer;
    transition: border-color 0.14s ease, background-color 0.14s ease, color 0.14s ease;
  }
  /* Keep per-application policy dropdown text & chevron colored while using a clean neutral outline */
  .styled-select-wrap.card-select-wrap .styled-select-trigger {
    height:auto;
    min-height:32px;
    padding:6px 10px;
    color:var(--app-accent, var(--text));
    background-color:#09090d;
    border:1px solid #22222c;
    font-size:10.5px;
    font-weight:800;
    text-transform:uppercase;
  }
  .styled-select-wrap.card-select-wrap .styled-select-trigger:hover,
  .styled-select-wrap.card-select-wrap.open .styled-select-trigger {
    background-color:#191926;
    border-color:#22222c;
    box-shadow:none;
  }
  .styled-select-wrap.filter-select-wrap { flex:0 0 156px; height:31px; }
  .styled-select-wrap.sort-select-wrap { flex:0 0 148px; height:31px; margin-left:0; }
  .styled-select-wrap.limit-unit-select-wrap { flex:0 0 74px; }
  .styled-select-trigger-label {
    min-width:0;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
  }
  .styled-select-chevron { flex:0 0 auto; color:var(--amber); font-size:9px; line-height:1; pointer-events:none; }
  .styled-select-wrap.card-select-wrap .styled-select-chevron {
    display:inline-block;
    color:var(--app-accent, var(--amber));
    font-size:10px;
  }
  .styled-native-select {
    position:absolute!important;
    width:1px!important;
    height:1px!important;
    padding:0!important;
    margin:-1px!important;
    overflow:hidden!important;
    clip:rect(0,0,0,0)!important;
    white-space:nowrap!important;
    border:0!important;
  }
  .styled-select-menu {
    position:fixed;
    z-index:1000;
    display:none;
    width:max-content;
    min-width:0;
    max-width:min(360px,calc(100vw - 16px));
    max-height:min(280px,calc(100vh - 16px));
    overflow-y:auto;
    overscroll-behavior:contain;
    padding:4px;
    color:var(--text);
    background:#101016;
    border:1px solid #30303b;
    box-shadow:0 12px 30px rgba(0,0,0,.55);
  }
  .styled-select-wrap.open .styled-select-menu { display:block; }
  .styled-select-option {
    display:block;
    width:100%;
    padding:6px 8px;
    color:var(--text);
    background:transparent;
    border:0;
    font:700 10px 'Segoe UI',system-ui,sans-serif;
    line-height:1.4;
    text-align:left;
    white-space:normal;
    overflow-wrap:anywhere;
    cursor:pointer;
  }
  .styled-select-option:hover, .styled-select-option[aria-selected="true"] {
    color:var(--app-accent, #fff);
    background:#1e1e28;
  }
  .styled-select-menu.card-select-menu .styled-select-option[aria-selected="true"] {
    border-left: 2px solid var(--app-accent, var(--amber));
    padding-left: 6px;
  }
  .view-switch { display:flex; align-items:center; gap:4px; }
  .view-switch .btn { padding:5px 9px; }
  .sort-select-wrap { margin-left:auto; }

  .router-toolbar {
    padding: 9px 18px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    background: var(--panel);
  }
  .locate-file-row { display:flex; gap:8px; align-items:center; }
  .locate-file-row input { flex:1; }
  .locate-file-row .btn { flex:0 0 auto; height:36px; padding:0 12px; display:inline-flex; align-items:center; }
  .studio-floating-tooltip {
    position:fixed;
    z-index:2000;
    pointer-events:none;
    display:none;
    max-width:320px;
    background:#101016;
    border:1px solid #30303b;
    padding:7px 10px;
    box-shadow:0 10px 26px rgba(0,0,0,.55);
    font:700 10px Consolas,monospace;
    color:#f59e0b;
    line-height:1.45;
  }
  .studio-floating-tooltip small {
    display:block;
    margin-top:2px;
    font:400 11px 'Segoe UI',system-ui,sans-serif;
    color:#d4d4d8;
  }
  .router-tool-group { display:flex; min-width:0; align-items:center; flex-wrap:wrap; gap:6px; }
  .router-tool-group:first-child { flex:1 1 auto; flex-wrap:nowrap; }
  .router-tool-group:last-child { flex:0 0 auto; justify-content:flex-end; margin-left:auto; }
  .view-switch { flex:0 0 auto; }
  .router-toolbar .btn { height:31px; padding:5px 10px; display:inline-flex; align-items:center; justify-content:center; }
  .adapter-limits {
    border-bottom:1px solid var(--hairline);
    background:#0b0b10;
  }
  .adapter-limits > summary {
    padding:9px 18px;
    color:var(--text);
    font:700 10px Consolas,monospace;
    letter-spacing:.4px;
    cursor:pointer;
    list-style:none;
  }
  .adapter-limits > summary::-webkit-details-marker { display:none; }
  .adapter-limits > summary::after { content:"+"; float:right; color:var(--amber); font-size:14px; }
  .adapter-limits[open] > summary::after { content:"−"; }
  .adapter-limit-note { padding:0 18px 9px; color:var(--muted); font-size:10px; line-height:1.5; }
  .adapter-limit-grid {
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
    gap:1px;
    background:var(--hairline);
  }
  .adapter-limit-card { background:#101016; padding:12px 14px; }
  .adapter-limit-title { margin-bottom:9px; font-size:12px; font-weight:800; }
  .adapter-limit-fields { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
  .adapter-limit-field { display:flex; flex-direction:column; gap:4px; color:var(--muted); font:700 9px Consolas,monospace; }
  .adapter-limit-field input {
    min-width:0;
    width:100%;
    height:30px;
    padding:5px 8px;
    color:var(--text);
    background:#09090d;
    border:1px solid #30303b;
    font:11px Consolas,monospace;
  }
  .adapter-limit-field input:focus, .adapter-limit-field select:focus { outline:none; border-color:var(--amber); }
  .limit-cycle-control { display:flex; gap:4px; }
  .adapter-limit-field .limit-cycle-control input { flex:1; }
  .adapter-limit-field .limit-cycle-control select {
    width:74px;
    color:var(--text);
    background:#09090d;
    border:1px solid #30303b;
    color-scheme:dark;
    font:10px Consolas,monospace;
  }
  .limit-mode-control { display:grid; gap:5px; }
  .limit-mode-control > input { width:100%; }
  .adapter-limit-field input:disabled { display:none; }
  .adapter-limit-meta { min-height:16px; margin-top:8px; color:var(--muted); font:10px Consolas,monospace; }
  .adapter-limit-meta.error, .modal-status.error { color:#f87171; }
  .adapter-limit-actions { display:flex; justify-content:flex-end; margin-top:8px; }
  .adapter-limit-actions .btn { height:29px; padding:4px 9px; }
  .adapter-limit-actions .btn:disabled { opacity:.55; cursor:wait; }
  .card-btn:disabled { opacity:.65; cursor:not-allowed; }
  .network-tuning-panel { width:min(500px,100%); }
  .tuning-options { display:grid; gap:9px; margin:16px 0; }
  .tuning-option {
    display:flex;
    align-items:flex-start;
    gap:10px;
    padding:11px 12px;
    background:#101016;
    border:1px solid #272732;
    color:var(--text);
    cursor:pointer;
  }
  .tuning-option input { accent-color:var(--amber); margin:2px 0 0; }
  .tuning-option strong { display:block; font-size:11px; }
  .tuning-option small { display:block; margin-top:3px; color:var(--muted); font-size:10px; line-height:1.5; }
  .tuning-limit-heading {
    margin:18px 0 8px;
    color:var(--amber);
    font:700 10px Consolas,monospace;
    letter-spacing:.5px;
  }
  .network-tuning-panel .adapter-limit-grid { margin-top:8px; }
  .network-tuning-panel .adapter-limit-card { border:1px solid #272732; }
  .network-tuning-panel .adapter-limit-fields { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .network-tuning-panel .adapter-limit-note { padding:0; }
  .modal-status { min-height:15px; margin-top:12px; color:var(--muted); font:10px Consolas,monospace; }
  .add-program-modal {
    position:fixed; inset:0; z-index:20; display:none;
    align-items:center; justify-content:center; padding:18px;
    background:rgba(0,0,0,.72);
  }
  .add-program-modal.open { display:flex; }
  .add-program-panel {
    width:min(460px,100%); max-height:min(90vh,620px); overflow:auto;
    background:#0c0c12; border:1px solid #30303b; border-top:2px solid var(--amber);
    padding:20px; box-shadow:0 18px 60px rgba(0,0,0,.6);
  }
  .add-program-panel h3 { font-size:15px; margin-bottom:18px; }
  .modal-field { display:flex; flex-direction:column; gap:7px; margin:13px 0; }
  .modal-field label { color:var(--muted); font:700 10px Consolas,monospace; text-transform:uppercase; }
  .modal-field select,.modal-field input {
    min-width:0; width:100%; background:#09090d; color:var(--text);
    border:1px solid #30303b; padding:9px 10px; font-size:12px;
  }
  .modal-field select {
    color-scheme: dark;
    appearance: none;
    padding-right: 34px;
    background-image: linear-gradient(45deg, transparent 50%, var(--amber) 50%), linear-gradient(135deg, var(--amber) 50%, transparent 50%);
    background-position: calc(100% - 15px) 50%, calc(100% - 11px) 50%;
    background-size: 4px 4px, 4px 4px;
    background-repeat: no-repeat;
  }
  .modal-field select option, .card-select option {
    color: var(--text);
    background: #0d0d12;
  }
  .modal-field select:focus, .modal-field input:focus {
    outline: none;
    border-color: var(--amber);
    box-shadow: 0 0 0 2px rgba(245, 158, 11, .14);
  }
  .modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }
  /* Two-row non-overlapping Chart Section */
  .chart-section {
    padding: 14px 18px 16px 18px;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .chart-row-1 {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .chart-row-2 {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 10px;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
  }
  .legend-pill { display: flex; align-items: center; gap: 6px; }
  .legend-dot { width: 8px; height: 8px; border-radius: 50%; }
  .canvas-box { position: relative; width: 100%; flex: 1; min-height: 250px; }
  canvas#telemetryChart { width: 100%; height: 100%; display: block; }
  .speed-summary { display:flex; align-items:center; gap:8px; font-family:'Consolas',monospace; font-size:11px; }
  .speed-chip { border:1px solid #272732; background:#14141d; padding:5px 8px; color:var(--amber); white-space:nowrap; }

  /* Unified Bottom Turbo Accelerator Container */
  .bottom-container { background: var(--panel); padding: 14px 20px 18px 20px; }
  .turbo-unified-box {
    margin-top: 10px;
    background: transparent;
    border: 0;
    padding: 0;
  }
  .dl-input-row { display: flex; gap: 8px; align-items: center; }
  .dl-url-input {
    flex: 1;
    background: #0c0c12;
    color: var(--text);
    border: 1px solid #22222c;
    padding: 9px 12px;
    font-family: 'Consolas', monospace;
    font-size: 12px;
    outline: none;
  }
  .dl-url-input:focus { border-color: var(--amber); }
  .progress-track {
    width: 100%;
    height: 8px;
    background: #12121a;
    margin-top: 10px;
    margin-bottom: 8px;
    overflow: hidden;
    position: relative;
  }
  .progress-fill {
    height: 100%;
    width: 0%;
    background: linear-gradient(90deg, var(--amber), var(--emerald), var(--cyan));
    transition: width 0.2s ease;
  }
  .dl-meta-row {
    display: flex;
    justify-content: space-between;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .block-strip { display: flex; flex-wrap: wrap; gap: 3px; min-height: 18px; }
  .blk { width: 12px; height: 10px; background: #181822; }
  @media (max-width: 720px) {
    .chart-section { min-height: 340px; }
    #appBentoGrid.list-view .bento-card { flex-direction: column; }
    .dl-input-row { flex-wrap:wrap; }
    .dl-url-input { min-width:180px; }
    .top-actions { justify-content:flex-end; }
  }
  @media (max-width: 560px) {
    .router-tool-group { width:100%; }
    .router-tool-group:first-child { flex-wrap:wrap; }
    .router-tool-group:last-child { margin-left:0; }
    .styled-select-wrap.sort-select-wrap { margin-left:0; flex:1 1 140px; }
    .router-tool-group:last-child .btn { flex:1; }
  }
</style>
</head>
<body>

  <div class="topbar">
    <div class="brand-row">
      <div class="ob-badge">OB</div>
      <div>
        <div class="brand-title">OmniBond</div>
        <div class="brand-sub" id="serverEndpoints">
          &bull; HTTP/HTTPS 127.0.0.1:8080 &nbsp;&bull; SOCKS5 127.0.0.1:1080 &nbsp;&bull; Web Dashboard 127.0.0.1:8085
        </div>
      </div>
    </div>
    <div class="top-actions">
      <button class="btn primary" id="btnSysProxy" title="Route all Windows HTTP/HTTPS & SOCKS5 traffic across active adapters" onclick="toggleSystemProxy()">◈ Bonding: Off</button>
      <button class="btn" title="Configure Windows multi-network and IP route optimization" onclick="openNetworkTuning()">⚙ Network Tuning</button>
      <button class="btn" title="Reset Windows proxy to Direct, restore automatic interface metrics, and flush DNS" onclick="repairNetwork()">✚ Repair Network</button>
      <button class="btn" id="btnGraphMode" aria-live="polite" aria-pressed="false" onclick="toggleGraphMode()">∿ Master Speed</button>
      <button class="btn" id="btnHideIps" aria-live="polite" aria-pressed="false" title="Hide or show all IP addresses across the dashboard" onclick="toggleHideIps()">👁 Hide IPs</button>
      <button class="btn" title="Re-scan Windows network adapters and IPv4 addresses" onclick="refreshAdapters()">⟳ Rescan Adapters</button>
    </div>
  </div>

  <div class="workspace-grid">
    <!-- 01 HARDWARE INTERFACES -->
    <div class="section-container">
      <div class="section-head">
        <div>
          <div class="kicker">01 / HARDWARE INTERFACES &middot; SOCKET BINDING</div>
          <div class="section-title">Active Network Adapters</div>
        </div>
        <div class="card-meta-links" id="adapterCountMeta">0 INTERFACES</div>
      </div>

      <div class="adapter-scroll" id="adapterScroll"><div class="bento-grid" id="adapterBentoGrid"></div></div>

      <div class="chart-section">
        <div class="chart-row-1">
          <span id="throughputSourceLabel" style="font-family:Consolas,monospace;font-size:11px;color:var(--muted);font-weight:700;">SYSTEM MULTI-NIC THROUGHPUT</span>
          <span class="speed-summary">
            <span class="speed-chip">LIVE <b id="liveTotalSpeed">0.0 KB/s</b></span>
            <span class="speed-chip">PEAK <b id="peakTotalSpeed">0.0 KB/s</b></span>
          </span>
        </div>
        <div class="chart-row-2" id="chartLegend"></div>
        <div class="canvas-box">
          <canvas id="telemetryChart" width="680" height="195"></canvas>
        </div>
      </div>
    </div>

    <!-- 02 APPLICATION ROUTER -->
    <div class="section-container">
      <div class="section-head">
        <div>
          <div class="kicker">02 / APPLICATION ROUTER &middot; GETEXTENDEDTCPTABLE PID ENGINE</div>
          <div class="section-title">Per-Application Network Pinning</div>
        </div>
        <div class="card-meta-links" id="pinnedCountMeta">RUNNING APPS</div>
      </div>

      <div class="router-toolbar">
        <div class="router-tool-group">
          <select class="filter-select" id="appFilterSelect" aria-label="Application category" title="Choose which application group to show" onchange="setProcFilter(this.value)">
            <option value="ALL">All programs</option>
            <option value="APPS">Apps</option>
            <option value="SERVICES">Services</option>
            <option value="FAVORITES">Favorites</option>
            <option value="MODIFIED">Modified bonding</option>
            <option value="UNMODIFIED">Default bonding</option>
          </select>
          <select class="sort-select" id="appSortSelect" aria-label="Sort applications" title="Sort apps by name or current network speed" onchange="setAppSort(this.value)">
            <option value="AZ">Name: A-Z</option>
            <option value="ZA">Name: Z-A</option>
            <option value="FAST">Speed: High–Low</option>
            <option value="SLOW">Speed: Low–High</option>
          </select>
          <div class="view-switch">
            <button class="btn active" id="gridViewBtn" onclick="setAppView('grid')">▦ Grid</button>
            <button class="btn" id="listViewBtn" onclick="setAppView('list')">☷ List</button>
          </div>
        </div>
        <div class="router-tool-group">
          <button class="btn" title="Scan running applications" onclick="loadRunningApps()">⌕ Scan</button>
          <button class="btn amber" title="Choose an application or built-in engine and its network policy" onclick="openAddProgram()">＋ Add Program</button>
        </div>
      </div>

      <div class="app-grid-scroll" id="appGridScroll"><div class="bento-grid" id="appBentoGrid"></div></div>
    </div>
  </div>

  <div class="add-program-modal" id="addProgramModal" role="dialog" aria-modal="true" aria-labelledby="addProgramTitle">
    <div class="add-program-panel">
      <h3 id="addProgramTitle">Add application to OmniBond</h3>
      <div class="modal-field">
        <label for="addAppSelect">Engine / application</label>
        <select id="addAppSelect"></select>
      </div>
      <div class="modal-field">
        <label for="customAppName">Or enter / locate an executable file</label>
        <div class="locate-file-row">
          <input id="customAppName" type="text" placeholder="e.g. game.exe">
          <button type="button" class="btn" title="Browse and select an executable file on disk" onclick="browseAppExecutable()">📂 Locate File</button>
          <input id="customAppFilePicker" type="file" accept=".exe,*/*" style="display:none" onchange="onCustomAppFilePicked(this)">
        </div>
      </div>
      <div class="modal-field">
        <label for="addPolicySelect">Network policy</label>
        <select id="addPolicySelect"></select>
      </div>
      <div class="modal-actions">
        <button class="btn" onclick="closeAddProgram()">Cancel</button>
        <button class="btn amber" onclick="submitAddProgram()">Add &amp; apply policy</button>
      </div>
    </div>
  </div>

  <div class="add-program-modal" id="networkTuningModal" role="dialog" aria-modal="true" aria-labelledby="networkTuningTitle">
    <div class="add-program-panel network-tuning-panel">
      <h3 id="networkTuningTitle">Network Tuning</h3>
      <div class="tuning-options">
        <label class="tuning-option">
          <input type="checkbox" id="tuneMultiNic">
          <span><strong>Keep multiple adapters active</strong><small>Disable Windows connection minimization so Wi-Fi, Ethernet, and tethering can remain available together.</small></span>
        </label>
        <label class="tuning-option">
          <input type="checkbox" id="tuneIpv4">
          <span><strong>Balance IPv4 routes</strong><small>Set active IPv4 interface metrics to the OmniBond preferred value.</small></span>
        </label>
        <label class="tuning-option">
          <input type="checkbox" id="tuneIpv6">
          <span><strong>Balance IPv6 routes</strong><small>Set active IPv6 interface metrics to the OmniBond preferred value.</small></span>
        </label>
      </div>
      <div class="tuning-limit-heading">PER-ADAPTER DATA &amp; SPEED LIMITS</div>
      <div class="adapter-limit-note">Data caps count all adapter traffic; at the cap, OmniBond excludes the adapter from new connections without disrupting existing ones or other Windows apps. Custom upload/download limits apply to OmniBond-routed traffic only. Choose Unlimited or Custom for each cap and speed.</div>
      <div class="adapter-limit-grid" id="adapterLimitGrid"></div>
      <div class="modal-status" id="networkTuningStatus"></div>
      <div class="modal-actions">
        <button class="btn" onclick="closeNetworkTuning()">Close</button>
        <button class="btn amber" onclick="optimizeMultiNic()">Apply settings</button>
      </div>
    </div>
  </div>

  <div class="add-program-modal" id="noticeModal" role="dialog" aria-modal="true" aria-labelledby="noticeTitle">
    <div class="add-program-panel">
      <h3 id="noticeTitle">OmniBond</h3>
      <p id="noticeMessage" style="color:var(--muted);font-size:12px;line-height:1.6;white-space:pre-line;"></p>
      <div class="modal-field" id="noticeInputWrap" style="display:none;">
        <label id="noticeInputLabel" for="noticeInput"></label>
        <input id="noticeInput" type="text">
      </div>
      <div class="modal-actions">
        <button class="btn" id="noticeCancelBtn">Cancel</button>
        <button class="btn amber" id="noticeConfirmBtn">OK</button>
      </div>
    </div>
  </div>

  <div class="studio-floating-tooltip" id="studioTooltip" role="tooltip"></div>
  <!-- 03 PARALLEL DOWNLOAD ENGINE -->
  <div class="bottom-container">
    <div class="kicker">03 / PARALLEL RANGE &amp; HLS (.M3U8) ENGINE &middot; ENDGAME RACING</div>
    <div class="section-title" style="margin-top:2px;">Download &amp; Stream Accelerator</div>

    <div class="turbo-unified-box">
      <div class="dl-input-row">
        <span style="font-family:Consolas,monospace;font-size:11px;color:var(--amber);font-weight:700;">URL</span>
        <input type="text" id="dlUrl" class="dl-url-input" placeholder="https://example.com/largefile.iso or https://example.com/stream.m3u8">
        <button class="btn primary" title="Download across bonded adapters using parallel HTTP ranges" onclick="startDownload()">⬇ Download</button>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="dlProgressFill"></div>
      </div>
      <div class="dl-meta-row">
        <span id="dlStatus">Ready &middot; Awaiting stream or file URL</span>
        <span id="dlTelemetry" style="color:var(--amber);font-weight:700;">0% &middot; 0.0 KB/s</span>
      </div>
      <div class="block-strip" id="blockGrid"></div>
    </div>
  </div>

<script>
let latestState = null;
let allProcesses = [];
let currentFilter = 'ALL';
let currentAppView = localStorage.getItem('omnibond-app-view') || 'grid';
let currentAppSort = localStorage.getItem('omnibond-app-sort') || 'AZ';
let hideIps = localStorage.getItem('omnibond-hide-ips') !== 'false';
let graphMode = localStorage.getItem('omnibond-graph-mode') === 'bonded' ? 'bonded' : 'master';
let peakTotalBps = 0;
let renderedAppStructure = '';
document.getElementById('appSortSelect').value = currentAppSort;

const APP_PALETTE_COLORS = [
  '#38bdf8', '#fb923c', '#34d399', '#a78bfa',
  '#facc15', '#f472b6', '#f87171', '#2dd4bf',
  '#818cf8', '#a3e635', '#e879f9', '#fb7185',
  '#60a5fa', '#fdba74', '#6ee7b7', '#fde047',
  '#22d3ee', '#c084fc', '#4ade80', '#f97316',
  '#f43f5e', '#14b8a6', '#eab308', '#ec4899'
];

function getAppAccentColor(idx) {
  return APP_PALETTE_COLORS[idx % APP_PALETTE_COLORS.length];
}

function maskIp(ip) {
  const s = String(ip || '').trim();
  if (!s || s === '-') return s || '-';
  return hideIps ? '•••.•••.•••.•••' : s;
}

function updateHideIpsButton() {
  const btn = document.getElementById('btnHideIps');
  if (!btn) return;
  btn.textContent = hideIps ? '👁 Show IPs' : '👁 Hide IPs';
  btn.classList.toggle('active', hideIps);
  btn.setAttribute('aria-pressed', String(hideIps));
}

function toggleHideIps() {
  hideIps = !hideIps;
  localStorage.setItem('omnibond-hide-ips', String(hideIps));
  updateHideIpsButton();
  renderedAppStructure = '';
  fetchState();
}

function setAppColorTheme(theme) {
  currentAppColorTheme = theme || 'MULTI';
  localStorage.setItem('omnibond-app-color', currentAppColorTheme);
  renderedAppStructure = '';
  if (latestState) fetchState();
}

function adapterSpeed(adapter) {
  return graphMode === 'master' ? (adapter.system_bps || 0) : (adapter.bps || 0);
}

function adapterSpeedHistory(adapter) {
  return graphMode === 'master' ? (adapter.system_bps_history || []) : (adapter.bps_history || []);
}

function appSpeed(app) {
  return app.bps || 0;
}

function appSpeedHistory(app) {
  return app.bps_history || [];
}

function updateGraphModeButton() {
  const button = document.getElementById('btnGraphMode');
  const master = graphMode === 'master';
  button.textContent = master ? '∿ Master Speed' : '⇄ Bonded Speed';
  button.classList.toggle('active', !master);
  button.setAttribute('aria-pressed', !master);
  button.title = master
    ? 'Showing live traffic on the computer network interfaces. Click to show OmniBond bonded traffic.'
    : 'Showing traffic routed through OmniBond bonding. Click to show overall computer network traffic.';
}

function toggleGraphMode() {
  graphMode = graphMode === 'master' ? 'bonded' : 'master';
  localStorage.setItem('omnibond-graph-mode', graphMode);
  peakTotalBps = 0;
  updateGraphModeButton();
  fetchState();
}

function fmtBytes(b) {
  if (!b || b <= 0) return '0 B';
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  if (b < 1073741824) return (b / 1048576).toFixed(2) + ' MB';
  return (b / 1073741824).toFixed(2) + ' GB';
}

function fmtDataBytes(b) {
  if (!b || b <= 0) return '0 B';
  if (b < 1000) return `${Math.round(b)} B`;
  if (b < 1_000_000) return `${(b / 1000).toFixed(1)} KB`;
  if (b < 1_000_000_000) return `${(b / 1_000_000).toFixed(2)} MB`;
  return `${(b / 1_000_000_000).toFixed(2)} GB`;
}

function fmtSpeed(bps) {
  if (!bps || bps < 1) return '0.0 KB/s';
  if (bps < 1048576) return (bps / 1024).toFixed(1) + ' KB/s';
  return (bps / 1048576).toFixed(2) + ' MB/s';
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function closeStyledSelects(except = null) {
  document.querySelectorAll('.styled-select-wrap.open').forEach(wrap => {
    if (wrap === except) return;
    wrap.classList.remove('open');
    wrap._styledMenu?.remove();
    wrap._styledMenu = null;
    wrap._styledTrigger?.setAttribute('aria-expanded', 'false');
  });
}

function positionStyledSelect(wrap) {
  const trigger = wrap._styledTrigger;
  const menu = wrap._styledMenu;
  if (!trigger || !menu) return;
  const rect = trigger.getBoundingClientRect();
  menu.style.left = '0px';
  menu.style.top = '0px';
  menu.style.minWidth = `${Math.min(Math.max(160, rect.width), window.innerWidth - 16)}px`;
  menu.style.maxWidth = `${Math.max(120, Math.min(360, window.innerWidth - 16))}px`;
  menu.style.maxHeight = `${Math.max(100, Math.min(280, window.innerHeight - 16))}px`;
  const menuWidth = menu.offsetWidth || rect.width;
  const menuHeight = Math.min(menu.scrollHeight, Math.max(100, Math.min(280, window.innerHeight - 16)));
  const below = window.innerHeight - rect.bottom - 8;
  const above = rect.top - 8;
  const placeAbove = below < Math.min(menuHeight, 150) && above > below;
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - menuWidth - 8));
  const top = placeAbove
    ? Math.max(8, rect.top - menuHeight - 4)
    : Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - menuHeight - 8));
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
}

function updateStyledSelectLabel(select) {
  const wrap = select.closest('.styled-select-wrap');
  if (!wrap?._styledLabel) return;
  const option = select.options[select.selectedIndex];
  wrap._styledLabel.textContent = option?.textContent?.trim() || 'Select';
  wrap._styledMenu?.querySelectorAll('[role="option"]').forEach((item, index) => {
    const selected = index === select.selectedIndex;
    item.setAttribute('aria-selected', String(selected));
  });
}

function syncStyledSelect(select) {
  if (!(select instanceof HTMLSelectElement)) return;
  let wrap = select.closest('.styled-select-wrap');
  if (!wrap) {
    wrap = document.createElement('span');
    const typeClass = select.classList.contains('card-select')
      ? 'card-select-wrap'
      : (select.classList.contains('filter-select')
        ? 'filter-select-wrap'
        : (select.classList.contains('sort-select')
          ? 'sort-select-wrap'
          : (select.classList.contains('color-select')
            ? 'color-select-wrap'
            : (select.dataset.limitField === 'cycle_unit' ? 'limit-unit-select-wrap' : ''))));
    wrap.className = `styled-select-wrap ${typeClass}`.trim();
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
  }
  const appAccent = select.style.getPropertyValue('--app-accent')?.trim() || select.dataset.appAccent || '';
  if (appAccent) {
    wrap.style.setProperty('--app-accent', appAccent);
  }
  let trigger = wrap._styledTrigger;
  if (!trigger) {
    trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'styled-select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const linkedLabel = select.id
      ? document.querySelector(`label[for="${CSS.escape(select.id)}"]`)?.textContent?.trim()
      : '';
    trigger.setAttribute('aria-label', select.getAttribute('aria-label') || linkedLabel || select.title || 'Choose an option');
    trigger.innerHTML = '<span class="styled-select-trigger-label"></span><span class="styled-select-chevron" aria-hidden="true">▾</span>';
    wrap.insertBefore(trigger, select);
    wrap._styledTrigger = trigger;
    wrap._styledLabel = trigger.querySelector('.styled-select-trigger-label');
    trigger.addEventListener('pointerdown', event => {
      event.stopPropagation();
      wrap._wasOpenOnPointerDown = wrap.classList.contains('open');
    });
    trigger.addEventListener('click', event => {
      event.stopPropagation();
      const shouldClose = wrap.classList.contains('open') || wrap._wasOpenOnPointerDown;
      wrap._wasOpenOnPointerDown = false;
      if (shouldClose) {
        closeStyledSelects();
        return;
      }
      closeStyledSelects(wrap);
      const menu = document.createElement('div');
      menu.className = select.classList.contains('card-select')
        ? 'styled-select-menu card-select-menu'
        : 'styled-select-menu';
      const currentAccent = wrap.style.getPropertyValue('--app-accent')?.trim();
      if (currentAccent) {
        menu.style.setProperty('--app-accent', currentAccent);
      }
      menu.style.display = 'block';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', trigger.getAttribute('aria-label'));
      Array.from(select.options).forEach((option, index) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = 'styled-select-option';
        item.setAttribute('role', 'option');
        item.setAttribute('aria-selected', String(index === select.selectedIndex));
        item.textContent = option.textContent.trim();
        item.disabled = option.disabled;
        item.addEventListener('click', () => {
          select.selectedIndex = index;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          closeStyledSelects();
          trigger.focus();
        });
        menu.appendChild(item);
      });
      document.body.appendChild(menu);
      wrap._styledMenu = menu;
      wrap.classList.add('open');
      trigger.setAttribute('aria-expanded', 'true');
      positionStyledSelect(wrap);
      const selected = menu.querySelector('[aria-selected="true"]:not(:disabled)');
      selected?.focus({ preventScroll: true });
      positionStyledSelect(wrap);
    });
    trigger.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        event.stopPropagation();
        trigger.click();
        const items = wrap._styledMenu?.querySelectorAll('[role="option"]:not(:disabled)');
        if (items?.length) items[event.key === 'ArrowUp' ? items.length - 1 : 0].focus();
      }
    });
  }
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');
  select.classList.add('styled-native-select');
  if (wrap._styledMenu) {
    wrap._styledMenu.replaceChildren();
    Array.from(select.options).forEach((option, index) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'styled-select-option';
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(index === select.selectedIndex));
      item.textContent = option.textContent.trim();
      item.disabled = option.disabled;
      item.addEventListener('click', () => {
        select.selectedIndex = index;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        closeStyledSelects();
        trigger.focus();
      });
      wrap._styledMenu.appendChild(item);
    });
    positionStyledSelect(wrap);
  }
  updateStyledSelectLabel(select);
}

function syncStyledSelects(root = document) {
  root.querySelectorAll('select').forEach(syncStyledSelect);
}

document.addEventListener('change', event => {
  if (event.target instanceof HTMLSelectElement) updateStyledSelectLabel(event.target);
});
/* Issue 7: Capture-phase pointerdown closes any open custom dropdown immediately when clicking anywhere else */
document.addEventListener('pointerdown', event => {
  const openWrap = document.querySelector('.styled-select-wrap.open');
  if (!openWrap) return;
  if (!openWrap.contains(event.target) && !openWrap._styledMenu?.contains(event.target)) {
    closeStyledSelects();
  }
}, true);
document.addEventListener('click', event => {
  if (!event.target.closest('.styled-select-wrap') && !event.target.closest('.styled-select-menu')) {
    closeStyledSelects();
  }
});
document.addEventListener('keydown', event => {
  const wrap = document.querySelector('.styled-select-wrap.open');
  if (!wrap) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeStyledSelects();
    wrap._styledTrigger?.focus();
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    const items = Array.from(wrap._styledMenu?.querySelectorAll('[role="option"]:not(:disabled)') || []);
    if (!items.length) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement);
    items[Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)))].focus();
  } else if (event.key === 'Enter' && document.activeElement?.matches('.styled-select-option')) {
    event.preventDefault();
    document.activeElement.click();
  }
});
window.addEventListener('resize', closeStyledSelects);
window.addEventListener('scroll', event => {
  if (event.target instanceof Element && event.target.closest('.styled-select-menu')) return;
  closeStyledSelects();
}, true);

function renderAdapterLimits(adapters) {
  const grid = document.getElementById('adapterLimitGrid');
  if (!grid || grid.contains(document.activeElement) || grid.querySelector('.styled-select-wrap.open')) return;
  grid.innerHTML = adapters.map(a => {
    const dataMode = a.data_limit_bytes ? 'custom' : 'unlimited';
    const downloadMode = a.download_limit_mbps > 0 ? 'custom' : 'unlimited';
    const uploadMode = a.upload_limit_mbps > 0 ? 'custom' : 'unlimited';
    const limitGb = a.data_limit_bytes ? (a.data_limit_bytes / 1_000_000_000).toFixed(3) : '';
    const usage = fmtDataBytes(a.usage_bytes || 0);
    const cap = a.data_limit_bytes ? fmtDataBytes(a.data_limit_bytes) : 'No data cap';
    const resetAt = new Date((a.period_started_at + a.cycle_hours * 3600) * 1000).toLocaleString();
    const cycleUnit = a.cycle_hours >= 24 && Math.abs(a.cycle_hours % 24) < 0.0001
      ? 'days'
      : (a.cycle_hours < 1 ? 'minutes' : 'hours');
    const cycleValue = cycleUnit === 'days'
      ? a.cycle_hours / 24
      : (cycleUnit === 'minutes' ? Math.round(a.cycle_hours * 60) : a.cycle_hours);
    const status = a.quota_exceeded
      ? 'LIMIT REACHED · excluded from new OmniBond connections'
      : `${usage} / ${cap} · window resets ${resetAt}`;
    return `
      <div class="adapter-limit-card">
        <div class="adapter-limit-title">${escapeHtml(a.name)} <span style="color:var(--muted);font-weight:500">· ${escapeHtml(a.kind)}</span></div>
        <div class="adapter-limit-fields">
          <label class="adapter-limit-field">DATA CAP
            <span class="limit-mode-control">
              <select data-limit-mode="data_limit_gb" aria-label="Data cap mode">
                <option value="unlimited" ${dataMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${dataMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="GB" value="${limitGb}" data-limit-field="data_limit_gb" ${dataMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
          <label class="adapter-limit-field">RESET WINDOW
            <span class="limit-cycle-control">
              <input type="number" min="1" step="0.01" value="${cycleValue}" data-limit-field="cycle_value">
              <select data-limit-field="cycle_unit" aria-label="Reset window unit">
                <option value="minutes" ${cycleUnit === 'minutes' ? 'selected' : ''}>min</option>
                <option value="hours" ${cycleUnit === 'hours' ? 'selected' : ''}>hours</option>
                <option value="days" ${cycleUnit === 'days' ? 'selected' : ''}>days</option>
              </select>
            </span>
          </label>
          <label class="adapter-limit-field">DOWNLOAD LIMIT (Mbps)
            <span class="limit-mode-control">
              <select data-limit-mode="download_limit_mbps" aria-label="Download speed limit mode">
                <option value="unlimited" ${downloadMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${downloadMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="Mbps" value="${a.download_limit_mbps || ''}" data-limit-field="download_limit_mbps" ${downloadMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
          <label class="adapter-limit-field">UPLOAD LIMIT (Mbps)
            <span class="limit-mode-control">
              <select data-limit-mode="upload_limit_mbps" aria-label="Upload speed limit mode">
                <option value="unlimited" ${uploadMode === 'unlimited' ? 'selected' : ''}>Unlimited</option>
                <option value="custom" ${uploadMode === 'custom' ? 'selected' : ''}>Custom</option>
              </select>
              <input type="number" min="0.001" step="any" placeholder="Mbps" value="${a.upload_limit_mbps || ''}" data-limit-field="upload_limit_mbps" ${uploadMode === 'unlimited' ? 'disabled' : ''}>
            </span>
          </label>
        </div>
        <div class="adapter-limit-meta">${status}</div>
        <div class="adapter-limit-actions">
          <button class="btn amber" data-adapter-name="${escapeHtml(a.name)}" onclick="saveAdapterLimits(this)">Save Limits</button>
        </div>
      </div>
    `;
  }).join('');
  syncStyledSelects(grid);
  grid.querySelectorAll('[data-limit-mode]').forEach(select => {
    select.addEventListener('change', () => {
      const input = select.closest('.adapter-limit-card')
        ?.querySelector(`[data-limit-field="${select.dataset.limitMode}"]`);
      if (!input) {
        console.error(`Missing input for adapter limit mode ${select.dataset.limitMode}.`);
        return;
      }
      input.disabled = select.value === 'unlimited';
      syncStyledSelect(select);
    });
  });
}

function splitAppTitle(displayName, appName = '') {
  if (displayName.includes('Turbo Accelerator')) return ['Turbo Accelerator', 'ENGINE'];
  if (appName && displayName && displayName.toLowerCase() !== appName.toLowerCase()) {
    return [displayName, appName];
  }
  const dot = displayName.lastIndexOf('.');
  if (dot > 0) {
    const base = displayName.slice(0, dot);
    return [base.charAt(0).toUpperCase() + base.slice(1), displayName];
  }
  return [displayName, appName || ''];
}

function setAppView(mode) {
  currentAppView = mode === 'list' ? 'list' : 'grid';
  localStorage.setItem('omnibond-app-view', currentAppView);
  document.getElementById('appBentoGrid').classList.toggle('list-view', currentAppView === 'list');
  document.getElementById('gridViewBtn').classList.toggle('active', currentAppView === 'grid');
  document.getElementById('listViewBtn').classList.toggle('active', currentAppView === 'list');
}

function setAppSort(mode) {
  currentAppSort = ['ZA', 'FAST', 'SLOW'].includes(mode) ? mode : 'AZ';
  localStorage.setItem('omnibond-app-sort', currentAppSort);
  if (latestState) fetchState();
}

function setProcFilter(cat) {
  currentFilter = cat;
  const select = document.getElementById('appFilterSelect');
  if (select && select.value !== cat) select.value = cat;
  fetchState();
}

function renderProcDropdown() {
  const sel = document.getElementById('addAppSelect');
  if (!sel) return;
  const prev = sel.value;
  let html = `<option value="__turbo_accelerator__">[ENGINE] Turbo Accelerator (Built-in)</option>`;
  for (const p of allProcesses) {
    const tag = p.category === 'USER APPS' ? 'APP' : (p.category === 'ACTIVE NET' ? 'NET' : 'SVC');
    const friendly = p.display_name && p.display_name.toLowerCase() !== p.exe_name.toLowerCase()
      ? `${p.display_name} (${p.exe_name})`
      : p.exe_name;
    const title = p.window_title ? ` — ${p.window_title.slice(0, 24)}` : '';
    const safeName = p.exe_name.replaceAll('"', '&quot;');
    html += `<option value="${safeName}">[${tag}] ${escapeHtml(friendly)} · PID ${p.pid}${escapeHtml(title)}</option>`;
  }
  sel.innerHTML = html;
  if (prev) sel.value = prev;
  syncStyledSelect(sel);
}

function matchesCurrentAppFilter(app) {
  if (currentFilter === 'APPS') return app.is_running && !app.is_builtin && app.category === 'USER APPS';
  if (currentFilter === 'SERVICES') {
    return app.is_running && ['SERVICES / BG', 'ACTIVE NET'].includes(app.category);
  }
  if (currentFilter === 'FAVORITES') return app.is_favorite;
  if (currentFilter === 'MODIFIED') return Boolean(app.rule && app.rule !== 'AUTO');
  if (currentFilter === 'UNMODIFIED') return !app.rule || app.rule === 'AUTO';
  return true;
}

function traceSmoothCatmullRom(ctx, pts, minY, maxY) {
  if (!pts.length) return;
  ctx.moveTo(pts[0].x, pts[0].y);
  const tension = 0.28;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const cp1x = p1.x + (p2.x - p0.x) * tension;
    const cp1y = Math.max(minY, Math.min(maxY, p1.y + (p2.y - p0.y) * tension));
    const cp2x = p2.x - (p3.x - p1.x) * tension;
    const cp2y = Math.max(minY, Math.min(maxY, p2.y - (p3.y - p1.y) * tension));
    ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
  }
}

function drawSparkline(canvas, history, color) {
  if (!canvas || !history || history.length < 2) return;
  const dpr = Math.max(2, window.devicePixelRatio || 1);
  const rect = canvas.getBoundingClientRect();
  const cssW = Math.max(120, rect.width || canvas.width || 190);
  const cssH = Math.max(26, rect.height || canvas.height || 32);
  if (canvas.width !== Math.floor(cssW * dpr) || canvas.height !== Math.floor(cssH * dpr)) {
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  const w = cssW;
  const h = cssH;
  ctx.clearRect(0, 0, w, h);

  let maxV = 4096;
  for (const v of history) if (v * 1.18 > maxV) maxV = v * 1.18;

  const minY = 3.5;
  const maxY = h - 3.5;
  const pts = history.map((v, i) => ({
    x: (i / (history.length - 1)) * (w - 8) + 3,
    y: maxY - Math.min(1, Math.max(0, v / maxV)) * (maxY - minY)
  }));

  ctx.beginPath();
  traceSmoothCatmullRom(ctx, pts, minY, maxY);
  const last = pts[pts.length - 1];
  ctx.lineTo(last.x, h - 1.5);
  ctx.lineTo(pts[0].x, h - 1.5);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, minY, 0, h - 1.5);
  grad.addColorStop(0, color + '40');
  grad.addColorStop(1, color + '02');
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.beginPath();
  traceSmoothCatmullRom(ctx, pts, minY, maxY);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.85;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(last.x, last.y, 2.4, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.restore();
}

function drawGoogleStyleChart(adapters) {
  const canvas = document.getElementById('telemetryChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = Math.max(2, window.devicePixelRatio || 1);
  const rect = canvas.getBoundingClientRect();
  if (canvas.width !== Math.floor(rect.width * dpr) || canvas.height !== Math.floor(rect.height * dpr)) {
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
  }
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';

  const w = rect.width;
  const h = rect.height;
  // Left-align Y-axis labels at x=0 (strictly flush with the 18px section padding)
  const padL = 68, padR = 12, padT = 10, padB = 22;
  const plotW = Math.max(1, w - padL - padR);
  const plotH = Math.max(1, h - padT - padB);

  ctx.clearRect(0, 0, w, h);

  let maxBps = 64 * 1024;
  for (const a of adapters) {
    for (const v of adapterSpeedHistory(a)) {
      if (v * 1.18 > maxBps) maxBps = v * 1.18;
    }
  }

  ctx.font = '10px Consolas, monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const rows = 4;
  for (let r = 0; r <= rows; r++) {
    const y = padT + (plotH / rows) * r;
    const val = maxBps * (1 - r / rows);
    ctx.strokeStyle = r === rows ? '#27272a' : '#18181f';
    ctx.setLineDash(r === rows ? [] : [3, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(w - padR, y);
    ctx.stroke();
    ctx.fillStyle = '#71717a';
    ctx.fillText(val <= 1 ? '0 B/s' : fmtSpeed(val), 0, y);
  }
  ctx.setLineDash([]);

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const xLabels = ['-60s', '-45s', '-30s', '-15s', 'LIVE'];
  for (let i = 0; i < xLabels.length; i++) {
    const x = padL + (plotW / (xLabels.length - 1)) * i;
    ctx.fillStyle = i === xLabels.length - 1 ? '#f59e0b' : '#52525b';
    ctx.fillText(xLabels[i], x, padT + plotH + 6);
  }

  adapters.forEach((a) => {
    const hist = adapterSpeedHistory(a);
    if (hist.length < 2) return;
    const pts = hist.map((v, idx) => ({
      x: padL + (idx / (hist.length - 1)) * plotW,
      y: padT + plotH - Math.min(1, Math.max(0, v / maxBps)) * plotH
    }));

    ctx.beginPath();
    traceSmoothCatmullRom(ctx, pts, padT, padT + plotH);
    const last = pts[pts.length - 1];
    ctx.lineTo(last.x, padT + plotH);
    ctx.lineTo(pts[0].x, padT + plotH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
    grad.addColorStop(0, a.color + '44');
    grad.addColorStop(1, a.color + '00');
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    traceSmoothCatmullRom(ctx, pts, padT, padT + plotH);
    ctx.strokeStyle = a.color;
    ctx.lineWidth = 2.2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  });

  ctx.restore();
}

async function fetchState() {
  try {
    const res = await fetch('/api/state');
    const st = await res.json();
    latestState = st;
    const epHost = maskIp('127.0.0.1');
    document.getElementById('serverEndpoints').textContent =
      `• HTTP/HTTPS ${epHost}:${st.http_port} • SOCKS5 ${epHost}:${st.socks_port} • Web Dashboard ${epHost}:${st.web_port}`;
    updateHideIpsButton();

    let totalBps = 0, enabledCnt = 0;
    st.adapters.forEach(a => { totalBps += adapterSpeed(a); if (a.enabled) enabledCnt++; });
    peakTotalBps = Math.max(peakTotalBps, totalBps);
    document.getElementById('liveTotalSpeed').textContent = fmtSpeed(totalBps);
    document.getElementById('peakTotalSpeed').textContent = fmtSpeed(peakTotalBps);
    document.getElementById('btnSysProxy').textContent = st.system_proxy ? '◈ Bonding: On' : '◈ Bonding: Off';
    document.querySelector('.topbar')?.classList.toggle('bonding-active', Boolean(st.system_proxy));
    updateGraphModeButton();
    const adapterTelemetryStatus = graphMode === 'master'
      ? st.system_adapter_telemetry_status
      : 'Adapter traffic routed through OmniBond';
    const adapterTelemetryLabel = graphMode === 'master'
      ? (adapterTelemetryStatus?.includes('unavailable') || adapterTelemetryStatus?.includes('did not match')
        ? 'SYSTEM NIC UNAVAILABLE'
        : 'SYSTEM NIC')
      : 'OMNIBOND';
    const adapterCountMeta = document.getElementById('adapterCountMeta');
    adapterCountMeta.textContent = `${enabledCnt} / ${st.adapters.length} INTERFACES BONDED · ${adapterTelemetryLabel}`;
    adapterCountMeta.title = adapterTelemetryStatus;
    const appCountMeta = document.getElementById('pinnedCountMeta');
    const appTelemetryStatus = st.system_app_telemetry_status || 'Per-app TCP telemetry status unavailable.';
    const appTelemetryLabel = appTelemetryStatus.startsWith('Administrator permission required')
      ? 'ADMIN REQUIRED'
      : (appTelemetryStatus.startsWith('Partial')
        ? 'PARTIAL TCP'
        : (appTelemetryStatus.includes('active') ? 'LIVE TCP'
          : (appTelemetryStatus.includes('waiting') ? 'WAITING TCP' : 'TCP STATUS')));
    appCountMeta.textContent = `${st.app_rules.length} ACTIVE / PINNED APPS · ${appTelemetryLabel}`;
    appCountMeta.title = `${appTelemetryStatus} OmniBond-proxied traffic is also tracked.`;
    document.getElementById('throughputSourceLabel').textContent = graphMode === 'master'
      ? 'MASTER SPEED · ALL COMPUTER NETWORK TRAFFIC'
      : 'BONDED SPEED · OMNIBOND ROUTED TRAFFIC';

    const sel = document.getElementById('addPolicySelect');
    const prevVal = sel.value;
    let opts = '<option value="AUTO">Auto / Bonded (All adapters)</option><option value="BLOCK">Block Internet</option>';
    st.adapters.forEach((a, i) => {
      opts += `<option value="${a.ip}">Pin to ${a.name} (${maskIp(a.ip)})</option>`;
    });
    if (sel.innerHTML !== opts) { sel.innerHTML = opts; if (prevVal) sel.value = prevVal; }
    syncStyledSelect(sel);

    // 01 Adapters
    document.getElementById('adapterBentoGrid').innerHTML = st.adapters.map((a, idx) => `
      <div class="bento-card">
        <div>
          <div class="card-top">
            <span class="num-badge" style="background:${a.color}">${String(idx + 1).padStart(2, '0')}</span>
            <span class="card-meta-links">IPV4 &middot; ${maskIp(a.ip)} &#8599;</span>
          </div>
          <div class="card-identity">
            <div class="card-icon" style="background:${a.badge_bg}">${a.kind.slice(0,2).toUpperCase()}</div>
            <div class="card-identity-text">
              <div class="card-name"><span class="card-title-main" title="${escapeHtml(a.name)}">${escapeHtml(a.name)}</span> <span class="card-title-ext" style="color:${a.color};border:1px solid ${a.color}44;">${escapeHtml(a.kind)}</span></div>
              <div class="card-desc">${a.latency_ms}ms RTT &middot; ${a.active_conns} Conns</div>
            </div>
          </div>
          <div class="status-box ${a.quota_exceeded ? 'quota-reached' : ''}">${a.quota_exceeded ? 'DATA CAP REACHED' : (a.enabled ? 'ACTIVE · ' + a.kind.toUpperCase() : 'DISABLED')}</div>
          <div style="font-size:11px;color:var(--dim);margin-bottom:8px;">
            Traffic: ${fmtBytes(graphMode === 'master' ? a.system_bytes_recv + a.system_bytes_sent : a.bytes_recv + a.bytes_sent)} &middot; Live: ${fmtSpeed(adapterSpeed(a))}
          </div>
        </div>
        <div class="card-actions">
          ${a.quota_exceeded
            ? '<button class="card-btn" disabled title="This adapter will rejoin OmniBond when its data window resets or the cap is removed">LIMIT REACHED · WAIT FOR RESET</button>'
            : `<button class="card-btn" title="Enable or disable this network adapter in the bonding pool" onclick="toggleAdapter('${escapeHtml(a.ip)}', ${!a.manually_enabled})">
                ${a.manually_enabled ? 'BONDED · CLICK TO TOGGLE' : 'DISABLED · CLICK TO ENABLE'}
              </button>`}
        </div>
      </div>
    `).join('');
    document.getElementById('adapterBentoGrid').style.minWidth = `${Math.max(100, st.adapters.length * 280)}px`;
    renderAdapterLimits(st.adapters);

    // 02 Applications with per-app speed sparklines & Focus button
    const visibleAppRules = st.app_rules.filter(matchesCurrentAppFilter);
    visibleAppRules.sort((a, b) => {
      if (currentAppSort === 'ZA') return b.display_name.localeCompare(a.display_name, undefined, {sensitivity: 'base'});
      if (currentAppSort === 'FAST') return appSpeed(b) - appSpeed(a) || a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
      if (currentAppSort === 'SLOW') return appSpeed(a) - appSpeed(b) || a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
      return a.display_name.localeCompare(b.display_name, undefined, {sensitivity: 'base'});
    });
    const appGrid = document.getElementById('appBentoGrid');
    const appPolicyFocused = Boolean(
      appGrid.querySelector('.card-select-wrap.open')
    );
    const appStructure = JSON.stringify([
      currentFilter,
      currentAppView,
      currentAppSort,
      hideIps,
      graphMode,
      visibleAppRules.map(r => r.app_name),
      visibleAppRules.map(r => [
        r.app_name, r.display_name, r.rule, r.is_favorite, r.is_running,
        r.category, r.last_pid, r.window_title
      ]),
      st.adapters.map(a => [a.ip, a.name])
    ]);
    if (!appPolicyFocused && appStructure !== renderedAppStructure) {
      appGrid.innerHTML = visibleAppRules.map((r, idx) => {
      const col = getAppAccentColor(idx);
      const [mainTitle, subExt] = splitAppTitle(r.display_name, r.app_name);
      const selectedRule = r.rule;
      let rowOpts = `<option value="AUTO" ${selectedRule === 'AUTO' ? 'selected' : ''}>Auto / Bonded</option>
        <option value="BLOCK" ${selectedRule === 'BLOCK' ? 'selected' : ''}>Block Internet</option>`;
      st.adapters.forEach(a => {
        rowOpts += `<option value="${a.ip}" ${selectedRule === a.ip ? 'selected' : ''}>${a.name} (${maskIp(a.ip)})</option>`;
      });
      const subText = r.rule === 'BLOCK'
        ? 'Internet Disabled'
        : (r.window_title
          ? r.window_title
          : (r.is_running
            ? (r.category === 'SERVICES / BG' ? `Background Service · PID ${r.last_pid || '-'}` : `Running Process · PID ${r.last_pid || '-'}`)
            : 'Pinned Rule'));

      return `
        <div class="bento-card" data-app-speed="${appSpeed(r)}">
          <div>
            <div class="card-top">
              <span class="num-badge" style="background:${col}">${String(idx + 1).padStart(2, '0')}</span>
              <div class="app-card-controls">
                <button class="favorite-btn ${r.is_favorite ? 'active' : ''}" title="${r.is_favorite ? 'Remove from favorites' : 'Add to favorites'}" onclick="toggleFavorite('${r.app_name}', ${!r.is_favorite})">${r.is_favorite ? '★' : '☆'}</button>
                <button class="focus-link" title="Bring the program window forward" onclick="focusApp('${r.app_name}', ${r.last_pid})">▣ Focus</button>
                <button class="card-btn" title="Open this program's file or installation location" onclick="locateApp('${r.app_name}', ${r.last_pid})">↗ Location</button>
              </div>
            </div>
            <div class="card-identity">
              <div class="card-icon" style="background:#14141d;color:${col};border:1px solid ${col}66;">${escapeHtml(mainTitle.slice(0,2).toUpperCase())}</div>
              <div class="card-identity-text">
                <div class="card-name" title="${escapeHtml(mainTitle)}${subExt ? ' (' + escapeHtml(subExt) + ')' : ''}">
                  <span class="card-title-main">${escapeHtml(mainTitle)}</span>
                  ${subExt ? `<span class="card-title-ext" style="color:${col};border:1px solid ${col}55;">${escapeHtml(subExt)}</span>` : ''}
                </div>
                <div class="card-desc" id="app_desc_${idx}" title="${escapeHtml(subText)}">${escapeHtml(subText)}</div>
              </div>
            </div>
            <div class="sparkline-box">
              <div class="sparkline-head">
                <span title="Direct TCP traffic attributed to this application, plus OmniBond-proxied traffic. UDP/QUIC is not included.">APP SPEED</span>
                <span id="app_speed_${idx}" style="color:${col};font-weight:700;">${fmtSpeed(appSpeed(r))}</span>
              </div>
              <canvas class="app-spark" id="spark_${idx}" width="190" height="32"></canvas>
            </div>
            <div id="app_summary_${idx}" style="font-size:10.5px;color:var(--dim);margin-bottom:12px;">
              IP: ${maskIp(r.last_adapter_ip)} &middot; Conns: ${r.active_connections} (${r.total_connections}) &middot; ${fmtBytes(r.bytes_transferred)}
            </div>
          </div>
          <div class="card-actions">
            <select class="card-select" id="app_policy_${idx}" data-app-name="${escapeHtml(r.app_name)}" data-app-accent="${col}" style="--app-accent:${col}" title="Select and apply a routing policy for ${escapeHtml(r.display_name)}" onchange="updateRuleInline('${r.app_name}', this.value)">
              ${rowOpts}
            </select>
          </div>
        </div>
      `;
      }).join('');
      syncStyledSelects(appGrid);
      setAppView(currentAppView);
      renderedAppStructure = appStructure;
    }
    visibleAppRules.forEach((r, idx) => {
      const col = getAppAccentColor(idx);
      const speedNode = document.getElementById(`app_speed_${idx}`);
      const summaryNode = document.getElementById(`app_summary_${idx}`);
      const descriptionNode = document.getElementById(`app_desc_${idx}`);
      if (speedNode) speedNode.textContent = fmtSpeed(appSpeed(r));
      if (summaryNode) {
        summaryNode.textContent =
          `IP: ${maskIp(r.last_adapter_ip)} · Conns: ${r.active_connections} (${r.total_connections}) · ${fmtBytes(r.bytes_transferred)}`;
      }
      if (descriptionNode) {
        const subText = r.rule === 'BLOCK'
          ? 'Internet Disabled'
          : (r.window_title
            ? r.window_title
            : (r.is_running
              ? (r.category === 'SERVICES / BG' ? `Background Service · PID ${r.last_pid || '-'}` : `Running Process · PID ${r.last_pid || '-'}`)
              : 'Pinned Rule'));
        descriptionNode.textContent = subText;
        descriptionNode.title = subText;
      }
      const cardNode = speedNode?.closest('.bento-card');
      if (cardNode) cardNode.dataset.appSpeed = String(appSpeed(r));
      drawSparkline(document.getElementById(`spark_${idx}`), appSpeedHistory(r), col);
    });

    // Legend & Main Chart
    document.getElementById('chartLegend').innerHTML = st.adapters.map((a, idx) => `
      <div class="legend-pill">
        <span class="legend-dot" style="background:${a.color}"></span>
        <span>${String(idx + 1).padStart(2, '0')} &middot; ${a.name} (<b>${fmtSpeed(adapterSpeed(a))}</b>)</span>
      </div>
    `).join('');
    drawGoogleStyleChart(st.adapters);

    // 03 Turbo
    const pct = Math.min(100, Math.max(0, st.turbo.progress_pct || 0));
    document.getElementById('dlProgressFill').style.width = `${pct}%`;
    document.getElementById('dlStatus').textContent = st.turbo.status_text;
    document.getElementById('dlTelemetry').textContent = `${pct.toFixed(0)}% · ${fmtSpeed(st.turbo.speed_bps)}`;
    document.getElementById('blockGrid').innerHTML = (st.turbo.blocks || []).map(b =>
      `<div class="blk" style="background:${b.status === 'pending' ? '#181822' : b.color}"></div>`
    ).join('');
  } catch (e) {
    console.error('Could not refresh OmniBond dashboard state.', e);
  }
}

async function loadRunningApps() {
  const res = await fetch('/api/processes');
  const data = await res.json();
  allProcesses = data.detailed || [];
  renderProcDropdown();
  fetchState();
}

async function updateRuleInline(appName, ruleVal) {
  const policyApp = document.activeElement?.closest?.('.card-select-wrap')
    ? document.activeElement.closest('.card-select-wrap').querySelector('select')?.dataset.appName
    : null;
  if (policyApp) document.activeElement.blur();
  const res = await fetch('/api/rules', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, rule: ruleVal})
  });
  if (!res.ok) {
    const data = await res.json();
    await showThemedDialog('Application Policy', data.message || 'Could not save this application policy.');
    return;
  }
  await fetchState();
  if (policyApp) {
    const matchingSelect = Array.from(document.querySelectorAll('.card-select'))
      .find(select => select.dataset.appName === policyApp);
    matchingSelect?.closest('.card-select-wrap')?._styledTrigger?.focus();
  }
}

async function toggleFavorite(appName, favorite) {
  const res = await fetch('/api/favorite', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, favorite})
  });
  if (!res.ok) await showThemedDialog('Favorites', (await res.json()).message || 'Could not update favorite.');
  await fetchState();
}

function showThemedDialog(title, message, options = {}) {
  closeStyledSelects();
  const modal = document.getElementById('noticeModal');
  const inputWrap = document.getElementById('noticeInputWrap');
  const input = document.getElementById('noticeInput');
  const cancel = document.getElementById('noticeCancelBtn');
  const confirm = document.getElementById('noticeConfirmBtn');
  const needsConfirmation = options.confirm === true || Boolean(options.inputLabel);
  document.getElementById('noticeTitle').textContent = title;
  document.getElementById('noticeMessage').textContent = message;
  document.getElementById('noticeInputLabel').textContent = options.inputLabel || '';
  inputWrap.style.display = options.inputLabel ? 'flex' : 'none';
  input.value = options.inputValue || '';
  cancel.style.display = needsConfirmation ? 'inline-flex' : 'none';
  confirm.textContent = options.confirmText || (needsConfirmation ? 'Continue' : 'OK');
  modal.classList.add('open');
  if (options.inputLabel) input.focus();
  else confirm.focus();
  return new Promise(resolve => {
    const finish = value => {
      modal.classList.remove('open');
      document.removeEventListener('keydown', onKeyDown);
      modal.onclick = null;
      resolve(value);
    };
    const onKeyDown = event => {
      if (event.key === 'Escape') finish(options.inputLabel ? null : false);
      if (event.key === 'Enter' && event.target === input) finish(input.value.trim());
    };
    confirm.onclick = () => finish(options.inputLabel ? input.value.trim() : true);
    cancel.onclick = () => finish(options.inputLabel ? null : false);
    modal.onclick = event => {
      if (event.target === modal) finish(options.inputLabel ? null : false);
    };
    document.addEventListener('keydown', onKeyDown);
  });
}

async function browseAppExecutable() {
  try {
    const res = await fetch('/api/browse_exe', {method: 'POST'});
    const data = await res.json();
    if (data && data.ok && data.app_name) {
      const input = document.getElementById('customAppName');
      input.value = data.app_name;
      input.dataset.fullLocation = data.location || '';
      return;
    }
    if (data && data.cancelled) return;
  } catch (_e) {}
  document.getElementById('customAppFilePicker')?.click();
}

function onCustomAppFilePicked(fileInput) {
  const file = fileInput?.files?.[0];
  if (!file) return;
  const input = document.getElementById('customAppName');
  input.value = file.name.toLowerCase();
  fileInput.value = '';
}

function openAddProgram() {
  closeStyledSelects();
  renderProcDropdown();
  const customInput = document.getElementById('customAppName');
  customInput.value = '';
  delete customInput.dataset.fullLocation;
  const modal = document.getElementById('addProgramModal');
  modal.classList.add('open');
  modal.onclick = event => {
    if (event.target === modal) closeAddProgram();
  };
  document.getElementById('addAppSelect').closest('.styled-select-wrap')?._styledTrigger?.focus();
}

function closeAddProgram() {
  closeStyledSelects();
  document.getElementById('addProgramModal').classList.remove('open');
}

async function submitAddProgram() {
  closeStyledSelects();
  const customName = document.getElementById('customAppName').value.trim();
  const appName = customName || document.getElementById('addAppSelect').value;
  const policy = document.getElementById('addPolicySelect').value || 'AUTO';
  if (!appName) return;
  await updateRuleInline(appName, policy);
  closeAddProgram();
}

async function locateApp(appName, pid) {
  let res = await fetch('/api/locate_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid})
  });
  let data = await res.json();
  if (data.ok) return;
  if (!await showThemedDialog('Program Location', `${data.message || 'No location is available.'}\n\nChoose the executable or installation folder now?`, {confirm: true, confirmText: 'Choose location'})) {
    return;
  }
  const location = await showThemedDialog('Program Location', 'Select the full executable file path or installed folder path.', {inputLabel: 'Executable or installation folder'});
  if (!location || !location.trim()) return;
  res = await fetch('/api/app_location', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, location: location.trim()})
  });
  data = await res.json();
  if (!res.ok || !data.ok) {
    await showThemedDialog('Program Location', data.message || 'Could not save this program location.');
    return;
  }
  res = await fetch('/api/locate_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid})
  });
  data = await res.json();
  if (!data.ok) await showThemedDialog('Program Location', data.message || 'Could not open this program location.');
}

async function focusApp(appName, pid) {
  const res = await fetch('/api/focus_app', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({app_name: appName, pid: pid})
  });
  const data = await res.json();
  if (!data.ok) await showThemedDialog('Application', data.message || 'Could not focus this application.');
}

async function toggleAdapter(ip, enabled) {
  await fetch('/api/adapter_toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ip, enabled})
  });
  fetchState();
}

async function toggleSystemProxy() { await fetch('/api/system_proxy', {method: 'POST'}); fetchState(); }
async function repairNetwork() {
  const res = await fetch('/api/repair_network', {method: 'POST'});
  const data = await res.json();
  await fetchState();
  await showThemedDialog('Network Repaired', data.message || 'Windows proxy and interface metrics restored to default.');
}
function openNetworkTuning() {
  closeStyledSelects();
  document.getElementById('tuneMultiNic').checked = localStorage.getItem('omnibond-tune-multi-nic') !== 'false';
  document.getElementById('tuneIpv4').checked = localStorage.getItem('omnibond-tune-ipv4') !== 'false';
  document.getElementById('tuneIpv6').checked = localStorage.getItem('omnibond-tune-ipv6') === 'true';
  document.getElementById('networkTuningStatus').textContent = '';
  const modal = document.getElementById('networkTuningModal');
  modal.classList.add('open');
  modal.onclick = event => {
    if (event.target === modal) closeNetworkTuning();
  };
}
function closeNetworkTuning() {
  closeStyledSelects();
  document.getElementById('networkTuningModal').classList.remove('open');
}
async function optimizeMultiNic() {
  const options = {
    keep_multi_nic: document.getElementById('tuneMultiNic').checked,
    ipv4: document.getElementById('tuneIpv4').checked,
    ipv6: document.getElementById('tuneIpv6').checked
  };
  const status = document.getElementById('networkTuningStatus');
  try {
    const res = await fetch('/api/optimize_nic', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(options)
    });
    const data = await res.json();
    status.textContent = data.message || 'Network tuning settings updated.';
    status.classList.toggle('error', !res.ok);
    if (res.ok) {
      localStorage.setItem('omnibond-tune-multi-nic', options.keep_multi_nic);
      localStorage.setItem('omnibond-tune-ipv4', options.ipv4);
      localStorage.setItem('omnibond-tune-ipv6', options.ipv6);
    }
  } catch (error) {
    status.textContent = `Could not apply network tuning: ${error.message}`;
    status.classList.add('error');
  }
}
async function saveAdapterLimits(button) {
  const card = button.closest('.adapter-limit-card');
  const cycleValue = Number(card.querySelector('[data-limit-field="cycle_value"]').value);
  const cycleUnit = card.querySelector('[data-limit-field="cycle_unit"]').value;
  const cycleHours = cycleValue * (cycleUnit === 'days' ? 24 : (cycleUnit === 'minutes' ? 1 / 60 : 1));
  const valueFor = (field, label) => {
    const mode = card.querySelector(`[data-limit-mode="${field}"]`);
    if (mode?.value === 'unlimited') return 0;
    const input = card.querySelector(`[data-limit-field="${field}"]`);
    const value = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(value) || value <= 0) {
      input.focus();
      return { error: `Enter a value greater than zero for ${label}, or choose Unlimited.` };
    }
    return value;
  };
  if (!Number.isFinite(cycleHours) || cycleHours <= 0) {
    card.querySelector('[data-limit-field="cycle_value"]').focus();
    await showThemedDialog('Adapter limits', 'Reset window must be greater than zero.');
    return;
  }
  const dataLimit = valueFor('data_limit_gb', 'the data cap');
  const downloadLimit = valueFor('download_limit_mbps', 'the download limit');
  const uploadLimit = valueFor('upload_limit_mbps', 'the upload limit');
  const invalid = [dataLimit, downloadLimit, uploadLimit].find(value => typeof value === 'object');
  if (invalid) {
    await showThemedDialog('Adapter limits', invalid.error);
    return;
  }
  const payload = {
    adapter_name: button.dataset.adapterName,
    data_limit_gb: dataLimit,
    cycle_hours: cycleHours,
    download_limit_mbps: downloadLimit,
    upload_limit_mbps: uploadLimit
  };
  button.disabled = true;
  const status = card.querySelector('.adapter-limit-meta');
  try {
    const res = await fetch('/api/adapter_limits', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    status.textContent = data.message || (res.ok ? 'Adapter limits saved.' : 'Could not save adapter limits.');
    status.classList.toggle('error', !res.ok);
    if (res.ok) {
      button.blur();
      fetchState();
    }
  } catch (error) {
    status.textContent = `Could not save adapter limits: ${error.message}`;
    status.classList.add('error');
  } finally {
    button.disabled = false;
  }
}
async function simulateTrafficBurst() { await fetch('/api/simulate_burst', {method: 'POST'}); fetchState(); }
async function refreshAdapters() { await fetch('/api/refresh_adapters', {method: 'POST'}); fetchState(); }
async function startDownload() {
  const url = document.getElementById('dlUrl').value.trim();
  if (!url) return;
  await fetch('/api/download', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url, output_path: ''})
  });
  fetchState();
}


(function initStudioTooltip() {
  const tip = document.getElementById('studioTooltip');
  if (!tip) return;
  let activeEl = null;
  function positionTip(x, y) {
    const pad = 12;
    const tw = tip.offsetWidth || 220;
    const th = tip.offsetHeight || 44;
    let lx = x + 14;
    let ly = y + 18;
    if (lx + tw > window.innerWidth - pad) lx = Math.max(pad, x - tw - 10);
    if (ly + th > window.innerHeight - pad) ly = Math.max(pad, y - th - 10);
    tip.style.left = `${lx}px`;
    tip.style.top = `${ly}px`;
  }
  document.addEventListener('mouseover', event => {
    const el = event.target instanceof Element ? event.target.closest('[title], [data-studio-tip]') : null;
    if (!el) {
      activeEl = null;
      tip.style.display = 'none';
      return;
    }
    if (el.getAttribute('title')) {
      el.setAttribute('data-studio-tip', el.getAttribute('title'));
      el.removeAttribute('title');
    }
    const text = el.getAttribute('data-studio-tip');
    if (!text) return;
    activeEl = el;
    tip.textContent = text;
    tip.style.display = 'block';
    positionTip(event.clientX, event.clientY);
  });
  document.addEventListener('mousemove', event => {
    if (activeEl && tip.style.display === 'block') {
      positionTip(event.clientX, event.clientY);
    }
  });
  document.addEventListener('mouseout', event => {
    if (activeEl && (!event.relatedTarget || !activeEl.contains(event.relatedTarget))) {
      activeEl = null;
      tip.style.display = 'none';
    }
  });
  document.addEventListener('pointerdown', () => { tip.style.display = 'none'; }, true);
})();

syncStyledSelects();
loadRunningApps();
setAppView(currentAppView);
updateGraphModeButton();
updateHideIpsButton();
fetchState();
setInterval(fetchState, 1200);
</script>
</body>
</html>
"""
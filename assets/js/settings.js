/* =========================================================
   浏览设置 · 下滑自动加载 / 瀑布流列数 / 每批条数 / 返回顶部 / 懒加载
   全部设置存 localStorage, 刷新后自动生效。
   ========================================================= */
(function () {
  'use strict';
  var KEY = 'br_settings';
  var DEFAULTS = {
    autoLoad: false, cols: 'auto', pageSize: 24, backTop: true, lazy: true,
    imageOnly: false, keyNav: true, copyClose: false, themeAuto: false
  };
  var cfg = load();
  window.BR_SETTINGS = cfg;

  function load() {
    var o = {};
    for (var k in DEFAULTS) o[k] = DEFAULTS[k];
    try {
      var raw = localStorage.getItem(KEY);
      if (raw) { var p = JSON.parse(raw); for (var k2 in DEFAULTS) if (k2 in p) o[k2] = p[k2]; }
      // 兼容旧版单独存的 page_size
      var ps = parseInt(localStorage.getItem('br_page_size'), 10);
      if (ps === 24 || ps === 48 || ps === 72) o.pageSize = ps;
    } catch (e) {}
    return o;
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) {}
    try { localStorage.setItem('br_page_size', String(cfg.pageSize)); } catch (e) {}
  }
  function $(id) { return document.getElementById(id); }

  /* ---------- 应用设置到页面 ---------- */
  function applyCols() {
    var grid = document.querySelector('.grid-container');
    if (!grid) return;
    grid.style.columnCount = cfg.cols === 'auto' ? '' : cfg.cols;
  }
  function applyAll() {
    applyCols();
    if (window.BR_setPageSize) window.BR_setPageSize(cfg.pageSize);
    else if (window.BR_rerender) window.BR_rerender();
    updateBackTopVisibility();
    document.body.classList.toggle('image-only', !!cfg.imageOnly);
    if (window.BR_rerender) window.BR_rerender();  // 纯图模式改了卡片结构, 重渲染一次
  }

  // 主题跟随系统
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  function applyThemeAuto() {
    if (!mq) return;
    if (cfg.themeAuto) {
      document.documentElement.classList.toggle('is-dark', !mq.matches);
    }
  }
  function onSysThemeChange(e) {
    if (cfg && cfg.themeAuto) {
      document.documentElement.classList.toggle('is-dark', !e.matches);
      var b = document.getElementById('themeToggle');
      if (b) { var ic = b.querySelector('.theme-toggle__icon'); if (ic) ic.textContent = e.matches ? '☾' : '☀'; }
    }
  }
  if (mq) { try { mq.addEventListener('change', onSysThemeChange); } catch (e) { mq.addListener(onSysThemeChange); } }

  // 键盘翻页: 弹窗打开时 ← → 切上一张/下一张
  function onKeyNav(e) {
    if (!cfg.keyNav) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    if (!window.BR_modalOpen || !window.BR_modalOpen()) return;
    var tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    var ids = window.BR_visibleIds ? window.BR_visibleIds() : [];
    if (!ids.length) return;
    // 当前打开的是哪张: 从弹窗标题/数据里找不到, 用 DOM 里 .active 卡片或记录上次点击
    var cur = window.BR_currentId && window.BR_currentId();
    var idx = cur ? ids.indexOf(cur) : -1;
    var next = e.key === 'ArrowRight' ? idx + 1 : idx - 1;
    if (idx < 0) next = 0;
    if (next < 0 || next >= ids.length) return;
    e.preventDefault();
    if (window.BR_openById) window.BR_openById(ids[next]);
  }

  /* ---------- 面板开关 ---------- */
  function openPanel() {
    var m = $('settingsMask'); if (!m) return;
    m.classList.add('open'); m.setAttribute('aria-hidden', 'false');
  }
  function closePanel() {
    var m = $('settingsMask'); if (!m) return;
    m.classList.remove('open'); m.setAttribute('aria-hidden', 'true');
  }

  /* ---------- 返回顶部 ---------- */
  function updateBackTopVisibility() {
    var b = $('backTop'); if (!b) return;
    var show = !!cfg.backTop && (window.scrollY > 500);
    b.classList.toggle('show', show);
  }
  var scrollTick = false;
  function onScroll() {
    updateBackTopVisibility();
    if (!cfg.autoLoad || scrollTick) return;
    // 接近底部 320px 就补下一批
    var nearBottom = (window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 320);
    if (!nearBottom) return;
    if (!$('loadMoreWrap') || $('loadMoreWrap').style.display === 'none') return;
    scrollTick = true;
    // 给一点延迟, 避免连续触发; 加载完自动复位
    setTimeout(function () {
      var more = window.BR_loadMore ? window.BR_loadMore() : false;
      setTimeout(function () { scrollTick = false; }, more ? 400 : 0);
    }, 120);
  }

  /* ---------- 绑定控件 ---------- */
  function bind() {
    var btn = $('settingsBtn'), mask = $('settingsMask'), close = $('settingsClose');
    if (btn) btn.addEventListener('click', openPanel);
    if (close) close.addEventListener('click', closePanel);
    if (mask) mask.addEventListener('click', function (e) { if (e.target === mask) closePanel(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePanel(); });

    var auto = $('setAutoLoad'), cols = $('setCols'), size = $('setPageSize'),
        back = $('setBackTop'), lazy = $('setLazy'), reset = $('setReset'),
        imageOnly = $('setImageOnly'), keyNav = $('setKeyNav'),
        copyClose = $('setCopyClose'), themeAuto = $('setThemeAuto');
    if (auto) { auto.checked = !!cfg.autoLoad; auto.addEventListener('change', function () {
      cfg.autoLoad = auto.checked; save();
      toast(cfg.autoLoad ? '已开启下滑自动加载' : '已关闭，恢复点「加载更多」');
    }); }
    if (cols) { cols.value = cfg.cols; cols.addEventListener('change', function () {
      cfg.cols = cols.value; save(); applyCols();
    }); }
    if (size) { size.value = String(cfg.pageSize); size.addEventListener('change', function () {
      cfg.pageSize = parseInt(size.value, 10) || 24; save();
      if (window.BR_setPageSize) window.BR_setPageSize(cfg.pageSize);
      toast('每批加载 ' + cfg.pageSize + ' 条');
    }); }
    if (back) { back.checked = !!cfg.backTop; back.addEventListener('change', function () {
      cfg.backTop = back.checked; save(); updateBackTopVisibility();
    }); }
    if (lazy) { lazy.checked = !!cfg.lazy; lazy.addEventListener('change', function () {
      cfg.lazy = lazy.checked; save();
      toast('设置已保存，刷新后生效');
      if (window.BR_rerender) window.BR_rerender();
    }); }
    if (imageOnly) { imageOnly.checked = !!cfg.imageOnly; imageOnly.addEventListener('change', function () {
      cfg.imageOnly = imageOnly.checked; save();
      document.body.classList.toggle('image-only', cfg.imageOnly);
      if (window.BR_rerender) window.BR_rerender();
      toast(cfg.imageOnly ? '已切换纯图模式' : '已恢复完整卡片');
    }); }
    if (keyNav) { keyNav.checked = !!cfg.keyNav; keyNav.addEventListener('change', function () {
      cfg.keyNav = keyNav.checked; save();
    }); }
    if (copyClose) { copyClose.checked = !!cfg.copyClose; copyClose.addEventListener('change', function () {
      cfg.copyClose = copyClose.checked; save();
    }); }
    if (themeAuto) { themeAuto.checked = !!cfg.themeAuto; themeAuto.addEventListener('change', function () {
      cfg.themeAuto = themeAuto.checked; save();
      if (cfg.themeAuto) { applyThemeAuto(); toast('已开启主题跟随系统'); }
      else toast('已关闭，主题用手动选择');
    }); }
    if (reset) reset.addEventListener('click', function () {
      cfg = {}; for (var k in DEFAULTS) cfg[k] = DEFAULTS[k];
      window.BR_SETTINGS = cfg; save();
      if (auto) auto.checked = cfg.autoLoad;
      if (cols) cols.value = cfg.cols;
      if (size) size.value = String(cfg.pageSize);
      if (back) back.checked = cfg.backTop;
      if (lazy) lazy.checked = cfg.lazy;
      if (imageOnly) imageOnly.checked = cfg.imageOnly;
      if (keyNav) keyNav.checked = cfg.keyNav;
      if (copyClose) copyClose.checked = cfg.copyClose;
      if (themeAuto) themeAuto.checked = cfg.themeAuto;
      applyAll();
      toast('已恢复默认设置');
    });

    var bt = $('backTop');
    if (bt) bt.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    window.addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('keydown', onKeyNav);
    // 切页签/分类后重新按列数渲染一次 (grid 可能被重建)
    document.addEventListener('click', function (e) {
      if (e.target.closest('.tab, .chip')) setTimeout(applyCols, 50);
    });
  }

  function toast(msg) {
    var t = $('toast'); if (!t) return;
    t.textContent = msg; t.style.opacity = '1'; t.style.transform = 'translate(-50%,0)';
    clearTimeout(t._t); t._t = setTimeout(function () {
      t.style.opacity = '0'; t.style.transform = 'translate(-50%,20px)';
    }, 1800);
  }

  function init() { bind(); applyAll(); applyThemeAuto(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

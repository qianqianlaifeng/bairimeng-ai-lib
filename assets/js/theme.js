/* 日夜主题切换：默认夜晚，选择记在本地浏览器，两个页面共用。
   首屏的无闪烁初始化写在各页 <head> 里，这里只负责按钮交互与图标同步。 */
(function () {
  'use strict';
  var KEY = 'br_theme';
  var root = document.documentElement;
  var btn = document.getElementById('themeToggle');

  function isDark() { return root.classList.contains('is-dark'); }

  function syncButton() {
    if (!btn) return;
    var icon = btn.querySelector('.theme-toggle__icon');
    var dark = isDark();
    // 夜里显示太阳（点一下变白天），白天显示月亮（点一下变夜晚）
    if (icon) icon.textContent = dark ? '☀' : '☾';
    btn.setAttribute('aria-label', dark ? '切换日间模式' : '切换夜间模式');
    btn.setAttribute('title', dark ? '切换日间模式' : '切换夜间模式');
  }

  function setTheme(dark) {
    root.classList.toggle('is-dark', dark);
    try { localStorage.setItem(KEY, dark ? 'dark' : 'light'); } catch (e) { }
    syncButton();
  }

  if (btn) {
    btn.addEventListener('click', function () { setTheme(!isDark()); });
  }
  syncButton();
})();

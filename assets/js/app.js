/* =========================================================
   白日梦AI生成库 · 图片 / 视频 / 文本 提示词库 —— 前端逻辑
   数据均为开放内容，可自由查看与复制
   ---------------------------------------------------------
   紧凑记录格式（为减小体积）
   文本: [id,title,body,cat,author,lang,type,dev,srcIdx]
   图片: [id,title,body,cat,desc,cover]
   视频: [id,title,body,cat,desc,cover,videoUrl,model,author,lang,srcKey,bodyLang]
   ========================================================= */
(function () {
  'use strict';

  var PAGE_SIZE = 24;
  var state = {
    tab: 'image', cat: '', q: '', lang: '', sort: 'default', page: 1, openId: '',
    text: [], image: [], video: [], list: [], manifest: null, loading: {},
    chunks: { text: 0, image: 0, video: 0 },
    done: { text: false, image: false, video: false },
    chunkDone: { text: [], image: [], video: [] }
  };
  var $ = function (s) { return document.querySelector(s); };

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function fmtNum(n) {
    n = n || 0;
    if (n >= 10000) return (n / 10000).toFixed(1).replace('.0', '') + 'w';
    if (n >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'k';
    return String(n);
  }
  function toast(m) {
    var t = $('#toast');
    t.textContent = m; t.style.opacity = '1'; t.style.transform = 'translate(-50%,0)';
    clearTimeout(t._tid);
    t._tid = setTimeout(function () { t.style.opacity = '0'; t.style.transform = 'translate(-50%,20px)'; }, 1800);
  }
  function busy(on, msg) {
    $('#loading').style.display = on ? '' : 'none';
    if (msg) $('#loadingText').textContent = msg;
    $('#grid').style.opacity = on ? .35 : 1;
  }

  /* ---------- 稳定色相 ---------- */
  function hue(id) {
    var h = 2166136261, s = String(id);
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    h ^= h >>> 15; h = Math.imul(h, 2246822507);
    h ^= h >>> 13; h = Math.imul(h, 3266489909);
    h ^= h >>> 16;
    return Math.abs(h) % 360;
  }
  function grad(id) {
    var h = hue(id);
    return 'linear-gradient(135deg,hsl(' + h + ',68%,58%),hsl(' + ((h + 42) % 360) + ',72%,44%))';
  }

  function looksJson(s) {
    var t = String(s).trim();
    return (t.charAt(0) === '{' && t.charAt(t.length - 1) === '}') ||
           (t.charAt(0) === '[' && t.charAt(t.length - 1) === ']');
  }
  function excerpt(s, n) {
    s = String(s || '').replace(/\s+/g, ' ').trim();
    return s.length <= n ? s : s.slice(0, n) + '…';
  }
  function pool() { return state[state.tab] || []; }
  // 外部媒体一律经本机 /media 代理转发，浏览器只连 localhost
  function m(u) {
    if (!u) return '';
    try { return '/media?u=' + btoa(encodeURIComponent(u)); }
    catch (e) { return u; }
  }
  function catMap() {
    var m = state.manifest;
    if (state.tab === 'text') return m.cats;
    if (state.tab === 'video') return m.videoCats || {};
    return m.imageCats;
  }

  /* ---------- 记录展开 ---------- */
  function expandText(r) {
    var m = state.manifest;
    var c = m.cats[r[3]] || ['综合其他', '✨'];
    var key = Object.keys(m.sources)[r[8]];
    var src = m.sources[key] || ['', ''];
    return {
      id: r[0], kind: 'text', title: r[1], body: r[2], cat: r[3],
      catLabel: c[0], catIcon: c[1], author: r[4], lang: r[5], type: r[6],
      dev: !!r[7], chars: r[2].length, isJson: looksJson(r[2]),
      license: src[0], url: src[1], source: key, cover: ''
    };
  }
  function expandImage(r) {
    var m = state.manifest;
    var c = m.imageCats[r[3]] || ['综合其他', '✨'];
    var src = m.sources['ai-image-prompts-skill'] || ['MIT', ''];
    return {
      id: r[0], kind: 'image', title: r[1], body: r[2], cat: r[3],
      catLabel: c[0], catIcon: c[1], desc: r[4], cover: r[5],
      author: 'YouMind OpenLab', lang: 'en', type: 'IMAGE', dev: false,
      chars: r[2].length, isJson: false, license: src[0], url: src[1],
      source: 'ai-image-prompts-skill'
    };
  }
  function expandVideo(r) {
    var m = state.manifest;
    var c = (m.videoCats || {})[r[3]] || ['综合其他', '🎬'];
    var key = r[10];
    var src = m.sources[key] || ['', ''];
    return {
      id: r[0], kind: 'video', title: r[1], body: r[2], cat: r[3],
      catLabel: c[0], catIcon: c[1], desc: r[4], cover: r[5],
      videoUrl: r[6], model: r[7], author: r[8], lang: r[9],
      license: src[0], url: src[1], source: key,
      bodyLang: r[11], type: 'VIDEO', dev: false,
      chars: r[2].length, isJson: looksJson(r[2])
    };
  }
  var EXPAND = { text: expandText, image: expandImage, video: expandVideo };

  /* ---------- 分类 ---------- */
  function currentCats() {
    var src = catMap();
    var cnt = {};
    pool().forEach(function (p) { cnt[p.cat] = (cnt[p.cat] || 0) + 1; });
    var out = Object.keys(cnt).map(function (k) {
      return { key: k, label: (src[k] || ['其他'])[0], icon: (src[k] || ['', '✨'])[1], n: cnt[k] };
    });
    out.sort(function (a, b) { return b.n - a.n; });
    return out;
  }

  function buildCategories() {
    var src = catMap();
    var cnt = (state.manifest && state.manifest.catCounts[state.tab]) || {};
    var keys = Object.keys(src);
    var total = 0;
    keys.forEach(function (k) { total += (cnt[k] || 0); });
    var items = keys.map(function (k) {
      return { key: k, label: src[k][0], icon: src[k][1], n: cnt[k] || 0 };
    }).sort(function (a, b) { return b.n - a.n; });

    var html = '<button class="chip active" data-cat="">全部<span class="cnt">' + fmtNum(total) + '</span></button>';
    items.forEach(function (c) {
      html += '<button class="chip" data-cat="' + esc(c.key) + '">' + c.icon + ' ' + esc(c.label) +
        '<span class="cnt">' + fmtNum(c.n) + '</span></button>';
    });
    var box = $('#categoriesScroll');
    box.innerHTML = html;
    box.onclick = function (e) {
      var b = e.target.closest('.chip');
      if (!b) return;
      box.querySelectorAll('.chip').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      state.cat = b.dataset.cat;
      state.page = 1;
      apply();
    };

    $('#popularLinks').innerHTML = items.slice(0, 9).map(function (c) {
      return '<a href="#" data-q="' + esc(c.label) + '">' + c.icon + ' ' + esc(c.label) + '</a>';
    }).join('');
    $('#popularLinks').onclick = function (e) {
      var a = e.target.closest('a[data-q]');
      if (!a) return;
      e.preventDefault();
      $('#searchInput').value = a.dataset.q;
      state.q = a.dataset.q; state.page = 1; apply();
    };
  }

  /* ---------- 过滤 ---------- */
  function apply() {
    var q = state.q.trim().toLowerCase();
    var list = pool().filter(function (p) {
      if (state.cat && p.cat !== state.cat) return false;
      if (state.tab !== 'image' && state.lang && p.lang !== state.lang) return false;
      if (!q) return true;
      return (p.title + ' ' + p.body + ' ' + p.catLabel + ' ' + (p.author || '') + ' ' +
        (p.desc || '') + ' ' + (p.model || ''))
        .toLowerCase().indexOf(q) !== -1;
    });
    if (state.sort === 'long') list.sort(function (a, b) { return b.chars - a.chars; });
    else if (state.sort === 'short') list.sort(function (a, b) { return a.chars - b.chars; });
    state.list = list;
    render();
  }

  /* ---------- 卡片 ---------- */
  function cardHtml(p) {
    var badges = '';
    if (p.kind === 'image') {
      badges = '<span class="badge img">图片</span>';
    } else if (p.kind === 'video') {
      badges = '<span class="badge vid">视频</span>';
      if (p.videoUrl) badges += '<span class="badge play">可播放视频</span>';
    } else {
      badges = '<span class="badge ' + (p.lang === 'zh' ? 'lang-zh' : 'lang-en') + '">' +
        (p.lang === 'zh' ? '中文' : 'EN') + '</span>';
      if (p.isJson) badges += '<span class="badge json">JSON</span>';
      if (p.dev) badges += '<span class="badge dev">DEV</span>';
    }

    // 封面：真实原图经 wsrv.nl 代理加载（国内可访问）；失败时回落到本地分类图
    var fb = 'assets/img/cat-' + p.cat + '.jpg';
    var coverImg = p.cover
      ? '<img class="cover" loading="lazy" src="' + esc(p.cover) + '"' +
        ' data-fb="' + esc(fb) + '"' +
        ' onload="this.parentNode.classList.add(\'has-img\')"' +
        ' onerror="this.onerror=null;this.src=this.getAttribute(\'data-fb\')" />'
      : '';
    // 视频：悬停时才挂载 src 播放，避免一次性拉取大量视频
    var hoverVid = (p.kind === 'video' && p.videoUrl)
      ? '<video class="hovervid" muted loop playsinline preload="none" data-src="' + esc(p.videoUrl) + '"></video>'
      : '';

    var cover = '<div class="card-cover" style="background:' + grad(p.id) + '">' +
      coverImg + hoverVid + badges +
      '<span class="cat-name">' + esc(p.catLabel) + '</span>' +
      (p.kind === 'video' && p.videoUrl ? '<span class="play-btn"></span>' : '') +
    '</div>';

    var meta = '<span>' + esc(p.kind === 'video' ? (p.model || p.catLabel) : p.catLabel) + '</span>';

    return '<div class="prompt-card" data-id="' + esc(p.id) + '">' + cover +
      '<div class="card-body">' +
        '<h3 class="card-title">' + esc(p.title) + '</h3>' +
        '<div class="card-excerpt">' + esc(excerpt(p.desc || p.body, 200)) + '</div>' +
        '<div class="card-foot">' + meta + '<span class="chars">' + fmtNum(p.chars) + ' 字</span></div>' +
      '</div>' +
    '</div>';
  }

  function render() {
    var shown = state.list.slice(0, state.page * PAGE_SIZE);
    $('#grid').innerHTML = shown.map(cardHtml).join('');
    $('#empty').style.display = state.list.length ? 'none' : '';
    $('#loadMoreWrap').style.display = shown.length < state.list.length ? '' : 'none';
    $('#resultCount').textContent = '（' + state.list.length + ' 条）';
    var active = $('#categoriesScroll .chip.active');
    var label = active ? active.textContent.replace(/\d+$/, '').trim() : '全部';
    $('#listTitle').firstChild.nodeValue = state.q ? '搜索“' + state.q + '”' : label;
    $('#hint').textContent = state.tab === 'image'
      ? '列表为图文卡片，点开查看完整提示词'
      : (state.tab === 'video' ? '悬停卡片可预览；点开查看完整提示词与视频' : '');
  }

  /* ---------- 详情 ---------- */
  function argHighlight(text) {
    // 高亮 {argument name="x" default="y"} 占位符
    return esc(text).replace(/\{argument\s+name=&quot;([^&]*?)&quot;\s+default=&quot;([^&]*?)&quot;\}/g,
      function (_, n, d) {
        return '<span class="arg">{argument <b>' + n + '</b> = <i>' + d + '</i>}</span>';
      });
  }

  function bodyHtml(p) {
    if (p.isJson) {
      var pretty;
      try { pretty = JSON.stringify(JSON.parse(p.body), null, 2); }
      catch (e) { pretty = p.body; }
      return '<pre class="code-block"><code>' + esc(pretty) + '</code></pre>';
    }
    return '<div class="prompt-text">' + argHighlight(p.body) + '</div>';
  }

  function openModal(id) {
    var p = pool().filter(function (x) { return x.id === id; })[0];
    if (!p) return;
    state.openId = id;

    $('#modalHead').style.background = grad(p.id);
    $('#mCat').textContent = p.catLabel;
    $('#mTitle').textContent = p.title;

    var pills = [];
    if (p.kind === 'image') pills.push('<span class="pill">图片提示词</span>');
    else if (p.kind === 'video') {
      pills.push('<span class="pill">视频提示词</span>');
      if (p.model) pills.push('<span class="pill">' + esc(p.model) + '</span>');
      pills.push('<span class="pill">正文 ' + (p.bodyLang === 'zh' ? '中文' : 'English') + '</span>');
      pills.push('<span class="pill">' + (p.videoUrl ? '可播放视频' : '仅封面') + '</span>');
    } else {
      pills.push('<span class="pill">' + (p.lang === 'zh' ? '中文' : 'English') + '</span>');
      pills.push('<span class="pill">' + esc(p.type) + '</span>');
      if (p.isJson) pills.push('<span class="pill">JSON 结构化</span>');
      if (p.dev) pills.push('<span class="pill">开发向</span>');
    }
    pills.push('<span class="pill">' + fmtNum(p.chars) + ' 字</span>');
    $('#mMeta').innerHTML = pills.join('');

    // 媒体区：视频优先播放，其次封面（原图经 wsrv.nl 代理；失败回落本地分类图）
    var media = $('#mMedia');
    var mfb = 'assets/img/cat-' + p.cat + '.jpg';
    if (p.kind === 'video' && p.videoUrl) {
      media.innerHTML = '<video class="preview-video" controls playsinline preload="metadata" ' +
        (p.cover ? 'poster="' + esc(p.cover) + '" ' : '') +
        'src="' + esc(p.videoUrl) + '"></video>';
    } else if (p.cover) {
      media.innerHTML = '<img class="preview" src="' + esc(p.cover) + '" ' +
        'data-fb="' + esc(mfb) + '" ' +
        'onerror="this.onerror=null;this.src=this.getAttribute(\'data-fb\')" />';
    } else {
      media.innerHTML = '';
    }

    var descTitle = p.kind === 'video' ? '画面说明' : '画面描述';
    $('#mDesc').innerHTML = p.desc
      ? '<div class="section-label">' + descTitle + '</div><div class="brief">' +
        esc(p.desc).replace(/\n/g, '<br/>') + '</div>' : '';

    $('#mBodyLabel').textContent = p.isJson ? '提示词全文（JSON，已格式化）' : '提示词全文';
    $('#mBody').innerHTML = bodyHtml(p);

    // 来源与授权信息不再对外展示
    $('#mSrc').innerHTML = '';
    $('#copyHint').textContent = '';
    $('#modalMask').classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    var v = $('#mMedia').querySelector('video');
    if (v) { try { v.pause(); } catch (e) {} }
    $('#mMedia').innerHTML = '';
    $('#modalMask').classList.remove('open');
    document.body.style.overflow = '';
  }

  /* ---------- 数据加载（分片懒加载） ---------- */
  // 数据已按 600 条/片拆分；首屏只取第 0 片，其余在后台渐进拉取，不阻塞渲染
  var LOAD_TIP = {
    text: '正在加载文本提示词…',
    image: '正在加载图片提示词…',
    video: '正在加载视频提示词…'
  };

  function loadChunk(tab, k, cb) {
    fetch('data/' + tab + '_' + k + '.json').then(function (r) { return r.json(); }).then(function (rows) {
      if (state.chunks[tab] === k) {
        Array.prototype.push.apply(state[tab], rows.map(EXPAND[tab]));
        state.chunks[tab] = k + 1;
      }
      cb(null);
    }).catch(function (e) { cb(e); });
  }

  function streamChunks(tab) {
    if (state.done[tab] || state.loading[tab]) return;
    var total = (state.manifest.chunks[tab] || 1);
    if (state.chunks[tab] >= total) { finishChunks(tab); return; }
    state.loading[tab] = 1;
    loadChunk(tab, state.chunks[tab], function (err) {
      state.loading[tab] = 0;
      if (err) { setTimeout(function () { streamChunks(tab); }, 1200); return; }
      if (state.chunks[tab] >= total) { finishChunks(tab); return; }
      streamChunks(tab);
    });
  }

  function finishChunks(tab) {
    if (state.done[tab]) return;
    state.done[tab] = true;
    (state.chunkDone[tab] || []).forEach(function (fn) { try { fn(); } catch (e) {} });
    state.chunkDone[tab] = [];
  }

  // 等待某 tab 全部分片加载完成（用于搜索前确保结果完整）
  function ensureAll(tab) {
    return new Promise(function (resolve) {
      if (state.done[tab]) return resolve();
      streamChunks(tab);
      var t = setInterval(function () {
        if (state.done[tab]) { clearInterval(t); resolve(); }
      }, 200);
      setTimeout(function () { clearInterval(t); resolve(); }, 60000);
    });
  }

  // 等待下一片加载完成（用于“加载更多”按需补充）
  function loadOneChunk(tab) {
    return new Promise(function (resolve) {
      var total = (state.manifest.chunks[tab] || 1);
      var start = state.chunks[tab];
      if (state.done[tab] || start >= total) { state.done[tab] = true; return resolve(); }
      streamChunks(tab);
      var t = setInterval(function () {
        if (state.chunks[tab] > start || state.done[tab]) { clearInterval(t); resolve(); }
      }, 150);
      setTimeout(function () { clearInterval(t); resolve(); }, 20000);
    });
  }

  function loadTab(tab, cb, silent) {
    if (state.chunks[tab] > 0) { cb(); return; }   // 已加载过第 0 片
    if (state.loading[tab]) return;
    state.loading[tab] = 1;
    if (!silent) busy(true, LOAD_TIP[tab] || '加载中…');
    fetch('data/' + tab + '_0.json').then(function (r) { return r.json(); }).then(function (rows) {
      state[tab] = rows.map(EXPAND[tab]);
      state.chunks[tab] = 1;
      state.loading[tab] = 0;
      if (!silent) busy(false);
      cb();
      streamChunks(tab);   // 后台渐进拉取其余分片
    }).catch(function (e) {
      state.loading[tab] = 0;
      if (!silent) busy(false);
      toast('数据加载失败：请检查网络后重试');
      console.error(e);
    });
  }

  function switchTab(tab) {
    if (state.tab === tab) return;
    state.tab = tab;
    state.cat = ''; state.page = 1; state.q = ''; state.lang = ''; state.sort = 'default';
    $('#searchInput').value = '';
    $('#langGroup').style.display = tab === 'image' ? 'none' : '';
    $('#langGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    $('#sortGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    document.querySelectorAll('.tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    loadTab(tab, function () { buildCategories(); apply(); });
  }

  /* ---------- 事件 ---------- */
  var hoverCard = null;

  function bind() {
    var grid = $('#grid');
    grid.addEventListener('click', function (e) {
      var c = e.target.closest('.prompt-card');
      if (c) openModal(c.dataset.id);
    });
    // 视频卡片：悬停才挂载并播放，离开即停止
    grid.addEventListener('mouseover', function (e) {
      var c = e.target.closest('.prompt-card');
      if (!c || c === hoverCard) return;
      hoverCard = c;
      var v = c.querySelector('video.hovervid');
      if (!v) return;
      if (!v.getAttribute('src')) v.setAttribute('src', v.dataset.src);
      c.classList.add('playing');
      var pr = v.play();
      if (pr && pr.catch) pr.catch(function () {});
    });
    grid.addEventListener('mouseout', function (e) {
      var c = e.target.closest('.prompt-card');
      if (!c) return;
      if (e.relatedTarget && c.contains(e.relatedTarget)) return;
      if (hoverCard === c) hoverCard = null;
      var v = c.querySelector('video.hovervid');
      c.classList.remove('playing');
      if (v) { try { v.pause(); v.currentTime = 0; } catch (err) {} }
    });

    $('#modalClose').addEventListener('click', closeModal);
    $('#modalMask').addEventListener('click', function (e) { if (e.target === $('#modalMask')) closeModal(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

    $('#searchBtn').addEventListener('click', doSearch);
    $('#searchInput').addEventListener('keydown', function (e) { if (e.key === 'Enter') doSearch(); });
    var timer;
    $('#searchInput').addEventListener('input', function () {
      clearTimeout(timer); timer = setTimeout(doSearch, 320);
    });
    function doSearch() {
      state.q = $('#searchInput').value; state.page = 1; apply();
      if (!state.done[state.tab]) {
        var q0 = state.q;
        ensureAll(state.tab).then(function () {
          if (state.q === q0) apply();
        });
      }
    }

    document.querySelectorAll('.tab').forEach(function (b) {
      b.addEventListener('click', function () { switchTab(b.dataset.tab); });
    });

    $('#langGroup').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-lang]');
      if (!b) return;
      $('#langGroup').querySelectorAll('button').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      state.lang = b.dataset.lang; state.page = 1; apply();
    });
    $('#sortGroup').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-sort]');
      if (!b) return;
      $('#sortGroup').querySelectorAll('button').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      state.sort = b.dataset.sort; state.page = 1; apply();
    });

    $('#loadMoreBtn').addEventListener('click', function () {
      var tab = state.tab, need = (state.page + 1) * PAGE_SIZE;
      function go() { state.page++; render(); }
      if (state[tab].length >= need || state.done[tab]) return go();
      busy(true, '加载更多…');
      loadOneChunk(tab).then(function () { busy(false); go(); });
    });

    $('#copyBtn').addEventListener('click', function () {
      var open = $('#modalMask').classList.contains('open');
      var txt = '';
      if (open) {
        var p = pool().filter(function (x) { return x.id === state.openId; })[0];
        txt = p ? p.body : $('#mBody').textContent;
      }
      var ok = function () { $('#copyHint').textContent = '✓ 已复制全文'; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(txt).then(ok, function () { fb(txt, ok); });
      } else { fb(txt, ok); }
    });
    function fb(text, cb) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); cb(); } catch (e) { toast('复制失败，请手动选择'); }
      document.body.removeChild(ta);
    }

    $('#logoLink').addEventListener('click', function (e) {
      e.preventDefault();
      state.cat = ''; state.q = ''; state.lang = ''; state.page = 1; state.sort = 'default';
      $('#searchInput').value = '';
      $('#langGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
      $('#sortGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
      buildCategories(); apply();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    $('#aboutLink').addEventListener('click', function (e) {
      e.preventDefault();
      document.getElementById('about').scrollIntoView({ behavior: 'smooth' });
    });
  }

  function stats() {
    var m = state.manifest;
    var total = (m.imageCount || 0) + (m.textCount || 0) + (m.videoCount || 0);
    var z = m.zh || { text: 0, image: 0, video: 0 };
    $('#statTotal').textContent = fmtNum(total);
    $('#statTotal2').textContent = fmtNum(total);
    $('#statVideo').textContent = fmtNum(m.videoCount || 0);
    $('#statPlay').textContent = fmtNum(m.videoPlayable || 0);
    $('#statCats').textContent = m.totalCats || 0;
    $('#tabTextCnt').textContent = fmtNum(m.textCount || 0);
    $('#tabImageCnt').textContent = fmtNum(m.imageCount || 0);
    $('#tabVideoCnt').textContent = fmtNum(m.videoCount || 0);
    $('#heroZh').textContent = fmtNum(z.text + z.video + z.image);
    $('#heroImage').textContent = fmtNum(m.imageCount || 0);
    $('#heroVideo').textContent = fmtNum(m.videoCount || 0);
    $('#heroVideoPlay').textContent = fmtNum(m.videoPlayable || 0);
  }

  function boot() {
    fetch('data/manifest.json').then(function (r) { return r.json(); }).then(function (m) {
      state.manifest = m;
      $('#langGroup').style.display = 'none';
      bind();
      stats();                       // 计数全部来自 manifest，瞬间渲染
      loadTab('image', function () { // 仅取第 0 片，其余后台渐进拉取
        buildCategories();
        apply();
      });
    }).catch(function (e) {
      $('#grid').innerHTML = '<div class="empty"><strong>数据加载失败</strong>' +
        '请刷新页面重试。若本地预览，请用 <code>python serve_free.py 8789</code> 启动服务器。</div>';
      console.error(e);
    });
  }

  boot();
})();

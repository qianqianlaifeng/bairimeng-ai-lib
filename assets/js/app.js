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
    tab: 'gal', cat: '', q: '', lang: '', sort: 'default', page: 1, openId: '',
    onlyRefs: false,
    text: [], image: [], video: [], gal: [], list: [], manifest: null, loading: {},
    fails: { text: 0, image: 0, video: 0, gal: 0 },
    chunks: { text: 0, image: 0, video: 0, gal: 0 },
    done: { text: false, image: false, video: false, gal: false },
    chunkDone: { text: [], image: [], video: [], gal: [] }
  };
  var $ = function (s) { return document.querySelector(s); };

  /* 图片代理前缀: 由 assets/js/config.js 的 IMG_BASE 决定。
     留空 = 同域; 填了 = 拼到前面(GitHub Pages 这类没有后端的静态托管用)。 */
  var IMG_BASE = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_BASE) || '';
  var IMG_FALLBACK = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_FALLBACK) || '';
  function coverUrl(u) {
    if (!u) return '';
    if (/^https?:\/\//.test(u)) return u;
    return IMG_BASE ? IMG_BASE.replace(/\/+$/, '') + u : u;
  }
  /* 主代理加载失败时, 自动把地址前缀换成备用代理重试一次(只换一次, 避免死循环) */
  if (IMG_FALLBACK) {
    document.addEventListener('error', function (e) {
      var el = e.target;
      if (!el || (el.tagName !== 'IMG' && el.tagName !== 'VIDEO')) return;
      var src = el.getAttribute('src') || '';
      var main = IMG_BASE.replace(/\/+$/, '');
      var fb = IMG_FALLBACK.replace(/\/+$/, '');
      if (main && fb && src.indexOf(main) === 0 && src.indexOf(fb) !== 0) {
        el.setAttribute('src', fb + src.slice(main.length));
        if (el.tagName === 'VIDEO') { try { el.load(); } catch (err) {} }
      }
    }, true);
  }
  /* 预热图片代理连接: 首屏几十张图, 提前做完 DNS + TLS 握手能省一大截等待 */
  [IMG_BASE, IMG_FALLBACK].forEach(function (b) {
    if (!b) return;
    var l = document.createElement('link');
    l.rel = 'preconnect'; l.href = b.replace(/\/+$/, ''); l.crossOrigin = 'anonymous';
    document.head.appendChild(l);
  });

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
  function mergeCats() {
    // 灵感画廊只装图片提示词，分类表就用画廊自己的，不再混视频分类。
    return state.manifest.galCats || {};
  }
  function catMap() {
    var m = state.manifest;
    if (state.tab === 'text') return m.cats;
    if (state.tab === 'video') return m.videoCats || {};
    if (state.tab === 'gal') return mergeCats();
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
      chars: r[2].length, isJson: looksJson(r[2]), refs: r[12] || [],
      fb: 'assets/img/cat-others.jpg'
    };
  }
  function expandGal(r) {
    var m = state.manifest;
    var c = (m.galCats || {})[r[3]] || ['综合其他', '✨'];
    return {
      id: r[0], kind: 'image', gal: true, title: r[1], body: r[2], cat: r[3],
      catLabel: c[0], catIcon: c[1], desc: r[4], cover: r[5],
      author: '', lang: 'zh', type: 'IMAGE', dev: false,
      chars: r[2].length, isJson: false, license: '', url: '',
      source: 'gal', fb: 'assets/img/cat-others.jpg', refs: r[6] || []
    };
  }
  var EXPAND = { text: expandText, image: expandImage, video: expandVideo, gal: expandGal };

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
      // 分类点下去如果一条都没有、而分片还没拉全 —— 说明该分类的数据还在后面，补齐再筛
      if (state.cat && !state.list.length && !state.done[state.tab]) {
        var t = state.tab;
        busy(true, '正在加载该分类…');
        ensureAll(t).then(function () { if (state.tab === t) { busy(false); apply(); } });
      }
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

  // 按分类 key 选中某个 chip（找不到就直接按 key 筛）
  function selectCat(key) {
    var box = $('#categoriesScroll');
    var b = box.querySelector('.chip[data-cat="' + esc(key || '') + '"]');
    if (b) { b.click(); return; }
    state.cat = key || ''; state.page = 1; apply();
  }

  /* ---------- 过滤 ---------- */
  function apply() {
    var q = state.q.trim().toLowerCase();
    var list = pool().filter(function (p) {
      if (state.cat && p.cat !== state.cat) return false;
      if (state.onlyRefs) {
        // 灵感画廊现在只装图片提示词，视频提示词在独立页签里。
        // 这里仍留一道兜底：画廊里只认带 gal 标记的图片条目。
        if (state.tab === 'gal' && !p.gal) return false;
        if (!(p.refs && p.refs.length)) return false;
      }
      if (state.tab !== 'gal' && state.lang && p.lang !== state.lang) return false;
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
  // 文本提示词的封面徽标（语言 / JSON / 开发向）
  function textBadges(p) {
    var b = '<span class="badge ' + (p.lang === 'zh' ? 'lang-zh' : 'lang-en') + '">' +
      (p.lang === 'zh' ? '中文' : 'EN') + '</span>';
    if (p.isJson) b += '<span class="badge json">JSON</span>';
    if (p.dev) b += '<span class="badge dev">DEV</span>';
    return b;
  }
  // 画廊/视频卡片只放媒体本体（对齐源站的排列）：图片与视频都按真实比例展示，
  // 不裁切；标题与分类改成悬停浮层。文本提示词没有封面图，保留原来的信息块。
  function cardHtml(p) {
    var fb = p.fb || ('assets/img/cat-' + p.cat + '.jpg');
    var isVid = p.kind === 'video' && p.videoUrl;
    var flowVid = isVid && !p.cover;      // 没海报图: 视频本体当封面, 比例由视频自己决定
    var ar = '3 / 4';
    var inner = '';
    if (flowVid) {
      // 视频本体当封面（按视频真实比例撑高）；万一视频加载不出来就退回分类图，
      // 不留空白块
      inner = '<video class="cover-flow" muted loop playsinline preload="metadata" ' +
        'src="' + esc(coverUrl(p.videoUrl)) + '" data-src="' + esc(coverUrl(p.videoUrl)) + '"' +
        ' onerror="this.style.display=\'none\';var w=this.parentNode;' +
        'w.classList.add(\'has-img\');w.style.backgroundImage=\'url(' + esc(fb) + ')\';' +
        'w.style.backgroundSize=\'cover\';w.style.backgroundPosition=\'center\'"></video>';
    } else if (p.cover) {
      // 封面按真实宽高比撑开容器（加载完成覆写 --ar），所以图片是完整展示而不是裁切
      inner = '<img class="cover" loading="lazy" src="' + esc(coverUrl(p.cover)) + '"' +
        ' data-fb="' + esc(fb) + '"' +
        ' onload="this.parentNode.classList.add(\'has-img\');' +
        'var r=this.naturalWidth/this.naturalHeight;' +
        'if(r>0.2&&r<5)this.parentNode.style.setProperty(\'--ar\',r.toFixed(3))"' +
        ' onerror="this.onerror=null;this.src=this.getAttribute(\'data-fb\')" />';
      if (isVid) {
        inner += '<video class="hovervid" muted loop playsinline preload="none" data-src="' +
          esc(coverUrl(p.videoUrl)) + '"></video>';
      }
    } else {
      inner = '<span class="cat-icon">' + esc(p.catIcon || '✨') + '</span>';
    }
    var cover = '<div class="card-cover' + (flowVid ? ' auto-ar' : '') + '"' +
      ' style="background:' + grad(p.id) + ';--ar:' + ar + '">' +
      inner +
      (isVid ? '<span class="play-btn"></span>' : '') +
      (p.kind === 'text' ? textBadges(p) :
        '<span class="tile-overlay"><b class="tile-title">' + esc(p.title) + '</b>' +
        '<i class="tile-cat">' + esc(p.catLabel) + '</i></span>') +
      '</div>';

    var body = '';
    if (p.kind === 'text') {
      body = '<div class="card-body">' +
        '<h3 class="card-title">' + esc(p.title) + '</h3>' +
        '<div class="card-excerpt">' + esc(excerpt(p.desc || p.body, 200)) + '</div>' +
        '<div class="card-foot"><span>' + esc(p.catLabel) + '</span>' +
        '<span class="chars">' + fmtNum(p.chars) + ' 字</span></div>' +
      '</div>';
    }
    return '<div class="prompt-card" data-id="' + esc(p.id) + '">' + cover + body + '</div>';
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
    $('#hint').textContent = state.onlyRefs
      ? '只看带风格参考图的图片条目（点开卡片可看参考图）'
      : (state.tab === 'gal'
        ? '图片提示词 · 点开卡片看完整提示词与风格参考'
        : (state.tab === 'video' ? '悬停卡片可预览；点开查看完整提示词与视频' : ''));
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
    if (p.gal) pills.push('<span class="pill">灵感画廊</span>');
    else if (p.kind === 'image') pills.push('<span class="pill">图片提示词</span>');
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

    // 媒体区：视频优先播放，其次封面（经图片代理；失败回落本地分类图）
    var media = $('#mMedia');
    var mfb = p.fb || ('assets/img/cat-' + p.cat + '.jpg');
    if (p.kind === 'video' && p.videoUrl) {
      media.innerHTML = '<video class="preview-video" controls playsinline preload="metadata" ' +
        (p.cover ? 'poster="' + esc(coverUrl(p.cover)) + '" ' : '') +
        'src="' + esc(coverUrl(p.videoUrl)) + '"></video>';
    } else if (p.cover) {
      media.innerHTML = '<img class="preview" src="' + esc(coverUrl(p.cover)) + '" ' +
        'data-fb="' + esc(mfb) + '" ' +
        'onerror="this.onerror=null;this.src=this.getAttribute(\'data-fb\')" />';
    } else {
      media.innerHTML = '';
    }

    var descTitle = p.kind === 'video' ? '画面说明' : '画面描述';
    $('#mDesc').innerHTML = p.desc
      ? '<div class="section-label">' + descTitle + '</div><div class="brief">' +
        esc(p.desc).replace(/\n/g, '<br/>') + '</div>' : '';

    // 风格参考：提示词里带的参考图(--sref/--cref 或开头输入图)，走同一个代理
    var refs = p.refs || [];
    var REF_LABEL = { sref: '风格', cref: '角色', dref: '构图', oref: '整体', ref: '输入图' };
    $('#mRefs').innerHTML = refs.length
      ? '<div class="section-label">风格参考</div><div class="ref-row">' +
        refs.map(function (rf) {
          var refUrl = rf[1];
          var t = REF_LABEL[rf[0]] || '参考';
          return '<a class="ref-item" href="' + esc(coverUrl(refUrl)) + '" target="_blank" rel="noopener">' +
            '<img src="' + esc(coverUrl(refUrl)) + '" loading="lazy" alt="' + esc(t) + '" ' +
            'onerror="this.parentNode.style.display=\'none\'" />' +
            '<span>' + esc(t) + '</span></a>';
        }).join('') + '</div>'
      : '<div class="section-label">风格参考</div><div class="ref-empty">该条没有风格参考图。<br/>' +
        '带参考图的卡片上有 <b>「风格参考」</b> 红色标记，也可以用工具栏的 <b>「✦ 只看风格参考」</b> 直接筛。</div>';

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
    gal: '正在加载灵感画廊…',
    video: '正在加载视频提示词…'
  };

  /* 分片清单：每个页签只装自己的分片。
     灵感画廊 = 画廊分片(图片提示词)，视频提示词在「视频提示词」页签里，两边不混。 */
  function shards(tab) {
    var m = state.manifest, out = [], i;
    var n = m.chunks[tab] || 1;
    for (i = 0; i < n; i++) out.push({ f: tab + '_' + i, k: tab });
    return out;
  }

  function loadChunk(tab, k, cb) {
    var d = shards(tab)[k];
    if (!d) return cb(null);
    fetch('data/' + d.f + '.json').then(function (r) { return r.json(); }).then(function (rows) {
      if (state.chunks[tab] === k) {
        Array.prototype.push.apply(state[tab], rows.map(EXPAND[d.k]));
        state.chunks[tab] = k + 1;
      }
      cb(null);
    }).catch(function (e) { cb(e); });
  }

  function streamChunks(tab) {
    if (state.done[tab] || state.loading[tab]) return;
    var total = shards(tab).length;
    if (state.chunks[tab] >= total) { finishChunks(tab); return; }
    state.loading[tab] = 1;
    loadChunk(tab, state.chunks[tab], function (err) {
      state.loading[tab] = 0;
      if (err) {
        // 分片缺失时不要无限重试(会让"加载更多"永远转圈)：连续失败 3 次就收尾
        state.fails[tab] = (state.fails[tab] || 0) + 1;
        if (state.fails[tab] >= 3) { finishChunks(tab); return; }
        setTimeout(function () { streamChunks(tab); }, 1200);
        return;
      }
      state.fails[tab] = 0;
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
      var total = shards(tab).length;
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
    var first = shards(tab)[0];
    fetch('data/' + (first ? first.f : tab + '_0') + '.json')
      .then(function (r) { return r.json(); }).then(function (rows) {
      state[tab] = rows.map(EXPAND[first ? first.k : tab]);
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

  // 图片提示词页已下线(2026-10-13): 看图片请去「灵感画廊」。这里保留白名单,
  // 旧链接 (?tab=image) 会自动落回灵感画廊。
  var TABS = ['gal', 'video', 'text'];

  function tabFromUrl() {
    var t = '';
    try { t = (new URLSearchParams(location.search).get('tab') || '').toLowerCase(); } catch (e) {}
    if (!t) t = (location.hash || '').replace(/^#/, '').toLowerCase();
    return TABS.indexOf(t) >= 0 ? t : '';
  }

  function syncUrl(tab) {
    try {
      var u = new URL(location.href);
      if (tab === 'gal') u.searchParams.delete('tab'); else u.searchParams.set('tab', tab);
      u.hash = '';
      history.replaceState(null, '', u.pathname + (u.search || ''));
    } catch (e) {}
  }

  function switchTab(tab) {
    if (state.tab === tab) return;
    state.tab = tab;
    state.cat = ''; state.page = 1; state.q = ''; state.lang = ''; state.sort = 'default';
    state.onlyRefs = false;
    if ($('#refGroup')) $('#refGroup').querySelector('button').classList.remove('active');
    $('#searchInput').value = '';
    $('#langGroup').style.display = (tab === 'gal') ? 'none' : '';
    $('#langGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    $('#sortGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    document.querySelectorAll('.tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    syncUrl(tab);
    loadTab(tab, function () {
      buildCategories();
      // 视频标签默认落在"热门视频": 这部分走本站代理、可播放、且带风格参考;
      // "全部"里另有 1040 条外链视频(国内可能加载不出来), 让用户自己点进去看
      if (tab === 'video') { selectCat('hotvideo'); return; }
      apply();
    });
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

    // 「只看风格参考」：打开时若池子还没拉全，先把分片拉完再筛，避免结果不全
    if ($('#refGroup')) $('#refGroup').addEventListener('click', function () {
      state.onlyRefs = !state.onlyRefs;
      $('#refGroup').querySelector('button').classList.toggle('active', state.onlyRefs);
      state.page = 1;
      apply();
      if (state.onlyRefs && !state.done[state.tab]) {
        var t = state.tab;
        busy(true, '正在汇总全部数据…');
        ensureAll(t).then(function () { if (state.tab === t) { busy(false); apply(); } });
      }
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
      state.onlyRefs = false;
      if ($('#refGroup')) $('#refGroup').querySelector('button').classList.remove('active');
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
    var total = (m.textCount || 0) + (m.videoCount || 0) + (m.galCount || 0);
    var z = m.zh || { text: 0, video: 0 };
    $('#statTotal').textContent = fmtNum(total);
    $('#statTotal2').textContent = fmtNum(total);
    $('#statVideo').textContent = fmtNum(m.videoCount || 0);
    $('#statPlay').textContent = fmtNum(m.videoPlayable || 0);
    $('#statCats').textContent = m.totalCats || 0;
    $('#tabTextCnt').textContent = fmtNum(m.textCount || 0);
    // 灵感画廊只装图片提示词，计数就是画廊自己的条数
    var galAll = m.galCount || 0;
    $('#tabGalCnt').textContent = fmtNum(galAll);
    $('#tabVideoCnt').textContent = fmtNum(m.videoCount || 0);
    $('#heroZh').textContent = fmtNum(z.text + z.video + (m.galCount || 0));
    if ($('#heroGal')) $('#heroGal').textContent = fmtNum(galAll);
    $('#heroVideo').textContent = fmtNum(m.videoCount || 0);
    $('#heroVideoPlay').textContent = fmtNum(m.videoPlayable || 0);
  }

  function boot() {
    fetch('data/manifest.json').then(function (r) { return r.json(); }).then(function (m) {
      state.manifest = m;
      var start = tabFromUrl() || 'gal';
      state.tab = start;
      $('#langGroup').style.display = (start === 'gal') ? 'none' : '';
      document.querySelectorAll('.tab').forEach(function (b) {
        b.classList.toggle('active', b.dataset.tab === start);
      });
      bind();
      stats();                       // 计数全部来自 manifest，瞬间渲染
      loadTab(start, function () {   // 仅取第 0 片，其余后台渐进拉取
        buildCategories();
        if (start === 'video') { selectCat('hotvideo'); return; }
        apply();
      });
    }).catch(function (e) {
      $('#grid').innerHTML = '<div class="empty"><strong>数据加载失败</strong>' +
        '请刷新页面重试。</div>';
      console.error(e);
    });
  }

  boot();
})();

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

  /* 图片地址处理分三层:
     1) IMG_BASE       —— 兼容保留: 相对路径拼前缀(留空 = 同域)
     2) IMG_SHRINK     —— 静态图床二次缩图: 把原图改写成 Worker 代理地址,
                          由 Cloudflare 侧转 webp + 限宽 600px
     3) IMG_FALLBACK   —— 备用代理(历史机制, 保留) */
  var IMG_BASE = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_BASE) || '';
  var IMG_FALLBACK = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_FALLBACK) || '';
  var IMG_SHRINK = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_SHRINK) || null;
  var SHRINK_HOSTS = (IMG_SHRINK && IMG_SHRINK.hosts) || [];
  var SHRINK_BASE = (IMG_SHRINK && IMG_SHRINK.base) || '';
  var SHRINK_TAG = (IMG_SHRINK && IMG_SHRINK.tag) || 'o';
  /* 视频/流媒体绝不走缩图代理: Worker 对 .mp4 等会原样流式转发, 但大文件在国内
     中间设备会 ECONNRESET(实测视频代理 0/3 成功), 且源站直连视频反而 206 正常(最快 379ms)。
     所以视频必须保持直连, 只给图片(静态图床原图)做代理缩图。 */
  var NO_SHRINK_EXT = /\.(mp4|webm|ogg|mov|m4v|m3u8|ts)(\?|$|#)/i;
  function shrinkUrl(u) {
    if (!SHRINK_BASE || !SHRINK_HOSTS.length) return '';
    if (NO_SHRINK_EXT.test(u)) return '';          // 视频/流媒体: 不代理
    var m = /^https?:\/\/([^\/]+)(\/.*)$/.exec(u);
    if (!m) return '';
    var host = m[1].toLowerCase();
    if (!SHRINK_HOSTS.some(function (h) { return host === h || host.slice(-h.length - 1) === '.' + h; })) return '';
    return SHRINK_BASE.replace(/\/+$/, '') + '/m/' + SHRINK_TAG + m[2];
  }
  function coverUrl(u) {
    if (!u) return '';
    if (/^https?:\/\//.test(u)) {
      var s = shrinkUrl(u);
      return s || u;
    }
    return IMG_BASE ? IMG_BASE.replace(/\/+$/, '') + u : u;
  }
  /* 缩图代理(Worker 域名在国内会间歇性被 RST)加载失败时, 自动回退到源图床原图。
     宁可慢一点、大一点, 也不能破图。回退只做一次。 */
  var SHRINK_PREFIX = SHRINK_BASE ? SHRINK_BASE.replace(/\/+$/, '') + '/m/' + SHRINK_TAG : '';
  function toOrig(src) {
    if (!SHRINK_PREFIX || src.indexOf(SHRINK_PREFIX) !== 0) return '';
    var tail = src.slice(SHRINK_PREFIX.length);   // 形如 /images/<id>/<n>.jpg
    var host = SHRINK_HOSTS.length ? SHRINK_HOSTS[0] : '';
    if (!host) return '';
    return 'https://' + host + tail;
  }
  document.addEventListener('error', function (e) {
    var el = e.target;
    if (!el || (el.tagName !== 'IMG' && el.tagName !== 'VIDEO')) return;
    var src = el.getAttribute('src') || '';
    // 1) 缩图代理 -> 源图床原图
    if (SHRINK_PREFIX && src.indexOf(SHRINK_PREFIX) === 0) {
      var orig = toOrig(src);
      if (orig) {
        el.setAttribute('src', orig);
        if (el.tagName === 'VIDEO') { try { el.load(); } catch (err) {} }
        return;
      }
    }
    // 2) 主代理 -> 备用代理
    if (!IMG_FALLBACK) return;
    var main = IMG_BASE.replace(/\/+$/, '');
    var fb = IMG_FALLBACK.replace(/\/+$/, '');
    if (main && fb && src.indexOf(main) === 0 && src.indexOf(fb) !== 0) {
      el.setAttribute('src', fb + src.slice(main.length));
      if (el.tagName === 'VIDEO') { try { el.load(); } catch (err) {} }
    }
  }, true);
  /* 预热图片代理连接: 首屏几十张图, 提前做完 DNS + TLS 握手能省一大截等待 */
  [IMG_BASE, IMG_FALLBACK, SHRINK_BASE].forEach(function (b) {
    if (!b) return;
    var l = document.createElement('link');
    l.rel = 'preconnect'; l.href = b.replace(/\/+$/, ''); l.crossOrigin = 'anonymous';
    document.head.appendChild(l);
  });

  /* data 分片缓存击穿: GitHub Pages 返回 max-age=600, 数据刷新(每日 Actions 或
     手动接入)后, 旧 manifest / 旧分片会在 CDN 上残留最多 10 分钟, 期间用户可能
     拿到"缺 wf 数据 / Vibe 页签空白"的旧版。make_ghpages 把 data/manifest.json
     的内容哈希写进 SITE_CONFIG.DATA_VER, 数据一变版本号就变, URL 随之改变,
     浏览器/CDN 都绕过缓存去取新文件。 */
  var DATA_VER = (window.SITE_CONFIG && window.SITE_CONFIG.DATA_VER) || '';
  function dataUrl(f) {
    return 'data/' + f + (DATA_VER ? '?v=' + DATA_VER : '');
  }

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
    // 黑金主题: 色相限定在琥珀-金区间, 不再全谱随机
    var h = 34 + (hue(id) % 24);
    return 'linear-gradient(135deg,hsl(' + h + ',74%,52%),hsl(' + ((h + 16) % 360) + ',80%,34%))';
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
    if (state.tab === 'vibe') return m.vibeCats || {};
    if (state.tab === 'h3') return m.h3Cats || {};
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
      // 「热门视频」那批是 AI 生成的静音片(实测文件里没有音轨)；
      // 其余来源(外链案例)带原声。标出来, 免得用户以为播放器坏了。
      silent: key === 'hotvideo',
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
  // Vibe Coding 行(14 字段): 尾缀 r[13]=media_type('image'/'video')决定渲染成图片卡还是视频卡
  function expandVibe(r) {
    var m = state.manifest;
    var c = (m.vibeCats || {})[r[3]] || ['Vibe Coding', '⚡'];
    var src = (m.sources || {})[r[10]] || ['', ''];
    var isVideo = (r[13] || 'video') !== 'image';
    return {
      id: r[0], title: r[1], body: r[2], cat: r[3], desc: r[4], cover: r[5],
      catLabel: c[0], catIcon: c[1], model: r[7], author: r[8], lang: r[9],
      license: src[0], url: src[1], source: r[10], refs: r[12] || [],
      dev: false, chars: (r[2] || '').length, isJson: looksJson(r[2]),
      fb: 'assets/img/cat-others.jpg',
      kind: isVideo ? 'video' : 'image', type: isVideo ? 'VIDEO' : 'IMAGE',
      videoUrl: isVideo ? r[6] : '', silent: false, bodyLang: r[11], gal: !isVideo
    };
  }
  // 海螺 H3 行(14 字段): 与 Vibe 同行结构, 分类表换成 h3Cats
  function expandH3(r) {
    var m = state.manifest;
    var c = (m.h3Cats || {})[r[3]] || ['H3 案例', '⚡'];
    var src = (m.sources || {})[r[10]] || ['', ''];
    var isVideo = (r[13] || 'video') !== 'image';
    return {
      id: r[0], title: r[1], body: r[2], cat: r[3], desc: r[4], cover: r[5],
      catLabel: c[0], catIcon: c[1], model: r[7], author: r[8], lang: r[9],
      license: src[0], url: src[1], source: r[10], refs: r[12] || [],
      dev: false, chars: (r[2] || '').length, isJson: looksJson(r[2]),
      fb: 'assets/img/cat-others.jpg',
      kind: isVideo ? 'video' : 'image', type: isVideo ? 'VIDEO' : 'IMAGE',
      videoUrl: isVideo ? r[6] : '', silent: false, bodyLang: r[11], gal: !isVideo
    };
  }
  var EXPAND = { text: expandText, image: expandImage, video: expandVideo, gal: expandGal, vibe: expandVibe, h3: expandH3 };

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
      inner = '<video class="cover-flow" muted loop playsinline preload="metadata" referrerpolicy="no-referrer" ' +
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
        inner += '<video class="hovervid" muted loop playsinline preload="none" referrerpolicy="no-referrer" data-src="' +
          esc(coverUrl(p.videoUrl)) + '"></video>';
      }
    } else {
      inner = '<span class="cat-icon">' + esc(p.catIcon || '✨') + '</span>';
    }
    var cover = '<div class="card-cover' + (flowVid ? ' auto-ar' : '') + '"' +
      ' style="background:' + grad(p.id) + ';--ar:' + ar + '">' +
      inner +
      (isVid ? '<span class="play-btn"></span>' : '') +
      (isVid && !p.silent ? '<span class="audio-badge" title="这条带原声">🔊</span>' : '') +
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
        : (state.tab === 'video'
          ? (state.cat === 'hotvideo'
            ? '⚠️ 当前「热门视频」是 AI 生成的静音画面（没有声音）；想听原声 → 点回「全部」或 动作 / 口播 / 音乐MV 等分类（卡片右下角有 🔊）'
            : '✦ 开放精选视频优先展示；进画面自动静音循环，点开卡片可听原声（右下角 🔊 的是带原声的）')
          : ''));
    // 静音默认分类给个醒目的黄条
    if ($('#hint')) $('#hint').classList.toggle('hint-warn', state.tab === 'video' && state.cat === 'hotvideo');
    // 卡片重画了, 重新挂一次自动播放的观察器
    startAutoplay();
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
    // 支持直接传对象（黑金轮播点击时从对应页签的数据池里找好再传入）
    var p = (id && typeof id === 'object') ? id
      : pool().filter(function (x) { return x.id === id; })[0];
    if (!p) return;
    state.openId = id;
    stopAutoplay();          // 弹窗里要放原声, 先把网格里的静音循环停掉

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

    // 媒体区：视频优先播放，其次封面（失败回落本地分类图）
    var media = $('#mMedia');
    var mfb = p.fb || ('assets/img/cat-' + p.cat + '.jpg');
    if (p.kind === 'video' && p.videoUrl) {
      // 点卡片算用户操作, 浏览器允许带声音自动播放 —— 有原声的直接出声
      media.innerHTML =
        '<div class="video-wrap">' +
          '<video class="preview-video" controls playsinline autoplay preload="metadata" referrerpolicy="no-referrer" ' +
          (p.cover ? 'poster="' + esc(coverUrl(p.cover)) + '" ' : '') +
          'src="' + esc(coverUrl(p.videoUrl)) + '"></video>' +
          '<div class="media-state" id="mVState"><span class="spin"></span>' +
          '<span id="mVStateTxt">视频加载中…</span></div>' +
          '<button class="sound-toggle" id="mVSound" type="button"></button>' +
        '</div>';
      var mv = media.querySelector('video');
      if (mv) {
        mv.volume = 1;
        var st = media.querySelector('#mVState');
        var stTxt = media.querySelector('#mVStateTxt');
        function hideState() { if (st) st.style.display = 'none'; }
        mv.addEventListener('playing', hideState);
        mv.addEventListener('canplay', hideState);
        mv.addEventListener('waiting', function () {
          if (st) { st.style.display = 'flex'; if (stTxt) stTxt.textContent = '视频加载中…'; }
        });
        mv.addEventListener('error', function () {
          if (st) { st.style.display = 'flex'; if (stTxt) stTxt.textContent = '视频加载失败（外链可能被网络拦截，可关闭重试）；带原声的也可换动作/口播/音乐MV 分类试试'; }
        });
        var pr = mv.play();
        if (pr && pr.catch) pr.catch(function () {
          // 带声音被拦了(极少见): 退回静音播放, 让用户点按钮开声音
          mv.muted = true;
          var pr2 = mv.play();
          if (pr2 && pr2.catch) pr2.catch(function () {});
        });
        // 声音开关按钮(显式手势, 万一带声音被拦也能一键开声)
        var sb = media.querySelector('#mVSound');
        if (sb) {
          if (p.silent) {
            sb.textContent = '🔇 无音轨';
            sb.classList.add('disabled');
            sb.disabled = true;
          } else {
            sb.textContent = mv.muted ? '🔇 已静音' : '🔊 声音已开';
            if (!mv.muted) sb.classList.add('on');
            sb.addEventListener('click', function () {
              if (mv.muted) {
                mv.muted = false; mv.volume = 1;
                var pp = mv.play(); if (pp && pp.catch) pp.catch(function () {});
                sb.textContent = '🔊 声音已开'; sb.classList.add('on');
              } else {
                mv.muted = true; sb.textContent = '🔇 已静音'; sb.classList.remove('on');
              }
            });
          }
        }
      }
    } else if (p.cover) {
      media.innerHTML = '<img class="preview" src="' + esc(coverUrl(p.cover)) + '" ' +
        'data-fb="' + esc(mfb) + '" ' +
        'onerror="this.onerror=null;this.src=this.getAttribute(\'data-fb\')" />';
    } else {
      media.innerHTML = '';
    }

    var descTitle = (p.source === 'oi' || /^oi-/.test(p.id)) ? '简介（中文）'
      : (p.kind === 'video' ? '画面说明' : '画面描述');
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

    // 无声片要讲清楚, 否则用户会以为是播放器坏了
    $('#mAudio').innerHTML = (p.kind === 'video' && p.videoUrl)
      ? '<div class="media-note ' + (p.silent ? 'note-silent' : 'note-audio') + '">' + (p.silent
        ? '🔇 这条是 AI 生成的画面，文件里<b>没有音轨</b>，所以放出来也没有声音（不是播放器坏了）。想听原声请去「动作 / 口播 / 音乐MV」等分类，卡片右下角有 🔊 标记。'
        : '🔊 这条<b>带原声</b>，点开即出声；若没声音，点右下角「🔊 声音已开」按钮或视频自带的喇叭即可。') +
        '</div>'
      : '';
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
    startAutoplay();          // 弹窗关了, 网格里的视频接着播
  }

  /* ---------- 数据加载（分片懒加载） ---------- */
  // 数据已按 600 条/片拆分；首屏只取第 0 片，其余在后台渐进拉取，不阻塞渲染
  var LOAD_TIP = {
    text: '正在加载文本提示词…',
    gal: '正在加载灵感画廊…',
    video: '正在加载视频提示词…',
    vibe: '正在加载 Vibe Coding…',
    h3: '正在加载海螺 H3…'
  };

  /* 分片清单：每个页签只装自己的分片。
     「开放精选」(oi_*) 排在最前 => 优先展示；后面跟原有分片。 */
  function shards(tab) {
    var m = state.manifest, out = [], i;
    // 外部图库(wf): 图片折进图库 / 视频折进视频页 / Vibe Coding 独立页签
    // 海螺 H3(h3): 独立页签, 行是 14 字段混合视频卡/图卡
    var wfKey = tab === 'vibe' ? 'wf_vibe' : (tab === 'gal' ? 'wf_image' : (tab === 'video' ? 'wf_video' : (tab === 'h3' ? 'h3_video' : '')));
    if (wfKey) {
      var nw = m.chunks[wfKey] || 0;
      for (i = 0; i < nw; i++) out.push({ f: wfKey + '_' + i, k: tab });
    }
    var no = (m.chunks['oi_' + tab]) || 0;
    for (i = 0; i < no; i++) out.push({ f: 'oi_' + tab + '_' + i, k: tab });
    var n = m.chunks[tab] || ((wfKey || no) ? 0 : 1);
    for (i = 0; i < n; i++) out.push({ f: tab + '_' + i, k: tab });
    return out;
  }

  function loadChunk(tab, k, cb) {
    var d = shards(tab)[k];
    if (!d) return cb(null);
    fetch(dataUrl(d.f + '.json')).then(function (r) { return r.json(); }).then(function (rows) {
      if (state.chunks[tab] === k) {
        Array.prototype.push.apply(state[tab], rows.map(EXPAND[d.k]));
        state.chunks[tab] = k + 1;
      }
      cb(null);
    }).catch(function (e) { cb(e); });
  }

  /* 自动后台预取的分片上限。
     首屏只需第 1 片即可渲染；再往前多备几片让"往下滚"顺滑。
     超过这个数就停下, 等用户点「加载更多」或搜索/筛选(需要全量)时再继续。
     好处: 不再一进站就把该页签全部分片拉完(oi_gal 15 片 + gal 79 片 ≈ 33MB),
     首屏带宽全留给图片, 而不是在后台空转下载用不到的数据。 */
  var AUTO_CHUNKS = 3;

  function streamChunks(tab, force) {
    if (state.done[tab] || state.loading[tab]) return;
    var total = shards(tab).length;
    if (state.chunks[tab] >= total) { finishChunks(tab); return; }
    // 自动流水线到上限就暂停(force=true 时不受限, 供搜索/筛选/加载更多使用)
    if (!force && state.chunks[tab] >= AUTO_CHUNKS) return;
    state.loading[tab] = 1;
    loadChunk(tab, state.chunks[tab], function (err) {
      state.loading[tab] = 0;
      if (err) {
        // 分片缺失时不要无限重试(会让"加载更多"永远转圈)：连续失败 3 次就收尾
        state.fails[tab] = (state.fails[tab] || 0) + 1;
        if (state.fails[tab] >= 3) { finishChunks(tab); return; }
        setTimeout(function () { streamChunks(tab, force); }, 1200);
        return;
      }
      state.fails[tab] = 0;
      if (state.chunks[tab] >= total) { finishChunks(tab); return; }
      streamChunks(tab, force);
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
      streamChunks(tab, true);   // force: 绕过自动预取上限, 真的拉完
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
      streamChunks(tab, true);   // force: 用户主动要更多, 不受自动上限限制
      var t = setInterval(function () {
        if (state.chunks[tab] > start || state.done[tab]) { clearInterval(t); resolve(); }
      }, 150);
      setTimeout(function () { clearInterval(t); resolve(); }, 20000);
    });
  }

  function loadTab(tab, cb, silent) {
    if (state.chunks[tab] > 0) { cb(); return; }   // 已加载过第 0 片
    if (state.loading[tab]) return;
    var list = shards(tab);
    if (!list.length) {                            // 该页签暂无分片(数据未刷新到 CDN / 空源): 显示空态
      state[tab] = state[tab] || [];
      state.chunks[tab] = 1;
      finishChunks(tab);
      cb();
      return;
    }
    state.loading[tab] = 1;
    if (!silent) busy(true, LOAD_TIP[tab] || '加载中…');
    var first = list[0];
    fetch(dataUrl(first.f + '.json'))
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
  var TABS = ['gal', 'video', 'text', 'vibe', 'h3'];

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
    $('#langGroup').style.display = (tab === 'gal' || tab === 'vibe' || tab === 'h3') ? 'none' : '';
    // 只有视频/Vibe 页有视频卡片, 自动播放开关就在那儿出现
    if ($('#autoplayGroup')) $('#autoplayGroup').style.display = (tab === 'video' || tab === 'vibe' || tab === 'h3') ? '' : 'none';
    $('#langGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    $('#sortGroup').querySelectorAll('button').forEach(function (x, i) { x.classList.toggle('active', i === 0); });
    document.querySelectorAll('.tab').forEach(function (b) {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
    syncUrl(tab);
    loadTab(tab, function () {
      buildCategories();
      // 视频页默认「全部」: 开放精选(oi)视频排在最前; 旧的热门静音视频在分类里按需筛
      apply();
    });
  }

  /* ---------- 视频自动播放 ----------
     视频卡片滚进视野就静音循环播放, 滚出去立刻停 —— 用 IntersectionObserver 管,
     避免一进页面几十个视频同时拉流量。浏览器只放行"静音自动播放", 所以必须 muted。 */
  var AUTOPLAY_KEY = 'brm_autoplay';
  var MAX_AUTOPLAY = 16;          // 同时播放上限(安全阀, 一般一屏也就十来个)
  var autoplayOn = true;
  var playObserver = null;
  var playingNow = [];

  function wantAutoplay() {
    var v = null;
    try { v = localStorage.getItem(AUTOPLAY_KEY); } catch (e) {}
    if (v === '0') return false;
    if (v === '1') return true;
    // 系统开了"减少动态效果"就默认关
    return !(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }
  function videoOf(card) {
    return card.querySelector('video.cover-flow') || card.querySelector('video.hovervid');
  }
  function playCard(card) {
    var v = videoOf(card);
    if (!v) return;
    if (!v.getAttribute('src')) {
      var s = v.getAttribute('data-src');
      if (s) v.setAttribute('src', s);
    }
    card.classList.add('playing');
    var pr = v.play();
    if (pr && pr.catch) pr.catch(function () {});
  }
  function pauseCard(card) {
    card.classList.remove('playing');
    var v = videoOf(card);
    if (v) { try { v.pause(); v.currentTime = 0; } catch (e) {} }
  }
  function stopAutoplay() {
    if (playObserver) playObserver.disconnect();
    document.querySelectorAll('#grid .prompt-card').forEach(pauseCard);
    playingNow = [];
  }
  function startAutoplay() {
    if (!autoplayOn) return;
    if (!playObserver) {
      playObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var c = en.target, i = playingNow.indexOf(c);
          if (en.isIntersecting) {
            if (i < 0) {
              if (playingNow.length >= MAX_AUTOPLAY) return;
              playingNow.push(c);
            }
            playCard(c);
          } else if (i >= 0) {
            playingNow.splice(i, 1);
            pauseCard(c);
          }
        });
      }, { threshold: 0.4 });
    }
    playObserver.disconnect();
    playingNow = [];
    document.querySelectorAll('#grid .prompt-card').forEach(function (c) {
      if (c.querySelector('video')) playObserver.observe(c);
    });
  }
  function setAutoplay(on) {
    autoplayOn = on;
    try { localStorage.setItem(AUTOPLAY_KEY, on ? '1' : '0'); } catch (e) {}
    var b = $('#autoplayBtn');
    if (b) {
      b.classList.toggle('active', on);
      b.textContent = on ? '⏸ 停自动播放' : '▶ 自动播放';
    }
    if (on) startAutoplay(); else stopAutoplay();
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
      // 开着自动播放时, 播放/停止一律由 IntersectionObserver 管, 鼠标移出不要抢
      if (autoplayOn) return;
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
    // 「自动播放」开关：默认开，关过一次就记住
    $('#autoplayBtn').addEventListener('click', function () { setAutoplay(!autoplayOn); });

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
  }

  function stats() {
    var m = state.manifest;
    var total = (m.textCount || 0) + (m.videoCount || 0) + (m.galCount || 0) + (m.vibeCount || 0) + (m.h3Count || 0);
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
    if ($('#tabVibeCnt')) $('#tabVibeCnt').textContent = fmtNum(m.vibeCount || 0);
    if ($('#tabH3Cnt')) $('#tabH3Cnt').textContent = fmtNum(m.h3Count || 0);
    $('#heroZh').textContent = fmtNum(z.text + z.video + (m.galCount || 0));
    if ($('#heroGal')) $('#heroGal').textContent = fmtNum(galAll);
    $('#heroVideo').textContent = fmtNum(m.videoCount || 0);
    $('#heroVideoPlay').textContent = fmtNum(m.videoPlayable || 0);
  }

  /* ---------- 黑金轮播（开放精选 · 自动滑动） ---------- */
  function renderHero() {
    var box = $('#heroCarousel');
    if (!box) return;
    var h = (state.manifest && state.manifest.oiHero) || [];
    if (!h.length) { box.style.display = 'none'; return; }
    var card = function (x, eager) {
      // 轮播封面同样要过 coverUrl(): 否则会用源图床原图(单张最大 1.2MB), 首屏等十几秒
      // eager 只给"首屏能看见的头几张", 其余交给浏览器按需解码
      return '<div class="hc-card" data-hid="' + esc(x.id) + '" data-hkind="' + x.kind + '" title="点开看提示词">' +
        '<img decoding="async"' + (eager ? ' fetchpriority="high"' : ' loading="lazy"') +
        ' src="' + esc(coverUrl(x.cover)) + '" alt="" onerror="this.style.opacity=.2" />' +
        '<div class="hc-meta"><b>' + esc(x.title) + '</b>' +
        '<i>' + (x.kind === 'video' ? '▶ 视频' : '🖼 图片') + '</i></div></div>';
    };
    // 列表复制一份做无缝循环; 卡片用 margin-right 而不是 gap, 保证两份宽度精确 = 200%
    // 1440 宽视口首屏只看得见 ~7 张, 前 10 张给高优先级, 其余走懒加载
    var EAGER = 10;
    var row = h.map(function (x, i) { return card(x, i < EAGER); })
      .concat(h.map(function (x) { return card(x, false); })).join('');
    // 轮播在最上面, 比网格更该先到手: 给首屏可见的头几张发 preload, 抢在网格之前排队
    var head = document.querySelector('head');
    h.slice(0, EAGER).forEach(function (x) {
      var u = coverUrl(x.cover);
      if (!u || !/^https?:\/\//.test(u)) return;
      var l = document.createElement('link');
      l.rel = 'preload'; l.as = 'image'; l.href = u;
      head.appendChild(l);
    });
    box.innerHTML = '<div class="hc-head"><span class="hc-t">✦ 开放精选 · 每日上新</span>' +
      '<span class="hc-tip">自动滑动 · 悬停暂停 · 点击看提示词</span></div>' +
      '<div class="hc-viewport"><div class="hc-track">' + row + '</div></div>';
    box.onclick = function (e) {
      var c = e.target.closest('.hc-card');
      if (c) openHero(c.dataset.hid, c.dataset.hkind);
    };
  }
  function openHero(id, kind) {
    var pools = ['gal', 'video', 'vibe'];
    function find() {
      for (var t = 0; t < pools.length; t++) {
        var arr = state[pools[t]] || [];
        for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
      }
      return null;
    }
    var it = find();
    if (it) { openModal(it); return; }
    // 轮播条目理论上在最前分片里; 万一还没加载(不在起始页), 把几个池都拉齐再找
    Promise.all(pools.map(function (t) { return ensureAll(t); })).then(function () {
      var it2 = find();
      if (it2) openModal(it2);
    });
  }

  function boot() {
    fetch(dataUrl('manifest.json')).then(function (r) { return r.json(); }).then(function (m) {
      state.manifest = m;
      var start = tabFromUrl() || 'gal';
      state.tab = start;
      $('#langGroup').style.display = (start === 'gal' || start === 'vibe' || start === 'h3') ? 'none' : '';
      if ($('#autoplayGroup')) $('#autoplayGroup').style.display = (start === 'video' || start === 'vibe' || start === 'h3') ? '' : 'none';
      document.querySelectorAll('.tab').forEach(function (b) {
        b.classList.toggle('active', b.dataset.tab === start);
      });
      bind();
      autoplayOn = wantAutoplay();     // 读用户的偏好（默认开）
      setAutoplay(autoplayOn);
      stats();                       // 计数全部来自 manifest，瞬间渲染
      renderHero();                  // 黑金轮播（开放精选）
      loadTab(start, function () {   // 仅取第 0 片，其余后台渐进拉取
        buildCategories();
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

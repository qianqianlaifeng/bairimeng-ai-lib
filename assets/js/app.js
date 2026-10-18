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
  var IMG_HOSTS = (window.SITE_CONFIG && window.SITE_CONFIG.IMG_HOSTS) || {};
  /* 画廊数据里的封面是 /m/<代号>/<路径> —— 用不到图床域名, 体积更小。
     但要能显示, 就得在这里把代号换回主机, 并补上各家图床的缩图参数
     (不补参数会拿到几 MB 的原图, 首屏 24 张直接卡死)。 */
  var IMG_HOST_QUERY = {
    i: '?x-oss-process=image/resize,w_600/format,webp/quality,q_80',
    q: '?imageMogr2/thumbnail/600x/format/webp/quality/80'
  };
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
    // /m/<代号>/<路径> -> 图床完整地址 + 该图床的缩图参数
    var m = /^\/m\/([a-z])\/(.+)$/.exec(u);
    if (m) {
      var host = IMG_HOSTS[m[1]];
      if (host) {
        var path = m[2];
        var q = IMG_HOST_QUERY[m[1]] || '';
        if (path.indexOf('?') !== -1) q = '';   // 路径自带参数就不再补
        return host.replace(/\/+$/, '') + '/' + path + q;
      }
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
    // 图片的兜底交给 app.js 里的 imgFail(分级: 代理->原图->图片代理->占位),
    // 这里只管视频, 避免两个处理器同时改 src 互相打断。
    if (!el || el.tagName !== 'VIDEO') return;
    var src = el.getAttribute('src') || '';
    // 1) 缩图代理 -> 源图床原图
    if (SHRINK_PREFIX && src.indexOf(SHRINK_PREFIX) === 0) {
      var orig = toOrig(src);
      if (orig) {
        el.setAttribute('src', orig);
        try { el.load(); } catch (err) {}
        return;
      }
    }
    // 2) 主代理 -> 备用代理
    if (!IMG_FALLBACK) return;
    var main = IMG_BASE.replace(/\/+$/, '');
    var fb = IMG_FALLBACK.replace(/\/+$/, '');
    if (main && fb && src.indexOf(main) === 0 && src.indexOf(fb) !== 0) {
      el.setAttribute('src', fb + src.slice(main.length));
      try { el.load(); } catch (err) {}
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

  /* ---------- 封面加载失败的兜底链 ----------
     部分图床对第三方 referer 直接 403(实测 media.openimages... 带 github.io 的 referer
     返回 403, 去掉 referer 才 200), 所以所有封面 img 都带 referrerpolicy="no-referrer"。
     万一某图床在当前网络仍取不到, 再退一层图片代理(服务端拉取, 不看 referer, 顺带缩到
     600px), 最后让卡片回到"渐变 + 分类图标"的占位 —— 绝不再把整屏换成同一张兜底图。 */
  var IMG_PROXY = 'https://wsrv.nl/?url=';
  function proxyUrl(u) {
    return /^https?:\/\//i.test(u) ? IMG_PROXY + encodeURIComponent(u) + '&w=600&output=webp' : '';
  }
  function imgFail(el) {
    if (!el) return;
    var stage = +(el.getAttribute('data-stage') || 0);
    var src = el.getAttribute('src') || '';
    /* 分级兜底, 每级只试一次:
       1) 缩图代理地址 -> 源图床原图(直连 + no-referrer 一般能过, 也比代理快)
       2) 图片代理(服务端拉取, 绕开本机网络对某个图床的限制)
       3) 占位: 渐变 + 分类图标 + 常显标题 —— 绝不整屏换成同一张兜底图 */
    if (stage === 0 && typeof toOrig === 'function') {
      var o = toOrig(src);
      if (o && o !== src) { el.setAttribute('data-stage', '1'); el.setAttribute('src', o); return; }
    }
    if (stage <= 1) {
      var p = proxyUrl(src);
      if (p) { el.setAttribute('data-stage', '2'); el.setAttribute('src', p); return; }
    }
    el.style.display = 'none';
    var w = el.parentNode;
    if (w && w.classList) w.classList.remove('has-img');
  }
  window.__imgFail = imgFail;

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
  // 开源 MiniMax H3 行(14 字段): 与 Vibe 同行结构, 分类表换成 h3Cats。
  // 数据只存相对媒体路径, 域名(config.js H3_MEDIA)在这里拼 —— 与 IMG_BASE 同款。
  function expandH3(r) {
    var m = state.manifest;
    var c = (m.h3Cats || {})[r[3]] || ['H3 案例', '⚡'];
    var src = (m.sources || {})[r[10]] || ['', ''];
    var isVideo = (r[13] || 'video') !== 'image';
    var h3base = (window.SITE_CONFIG && window.SITE_CONFIG.H3_MEDIA) || '';
    var h3u = function (p) {
      if (!p) return '';
      return /^https?:\/\//i.test(p) ? p : (h3base + p);
    };
    return {
      id: r[0], title: r[1], body: r[2], cat: r[3], desc: r[4], cover: h3u(r[5]),
      catLabel: c[0], catIcon: c[1], model: r[7], author: r[8], lang: r[9],
      license: src[0], url: src[1], source: r[10], refs: r[12] || [],
      dev: false, chars: (r[2] || '').length, isJson: looksJson(r[2]),
      fb: 'assets/img/cat-others.jpg',
      kind: isVideo ? 'video' : 'image', type: isVideo ? 'VIDEO' : 'IMAGE',
      videoUrl: isVideo ? h3u(r[6]) : '', silent: false, bodyLang: r[11], gal: !isVideo
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
      /* 先拉该分类的「首屏包」(单个小文件, 1~2 秒就有图), 再在后台按分片慢慢补全。
         全程不遮罩: 没数据时显示"正在加载该分类", 有数据就画, 条数持续增长。 */
      if (state.cat) {
        var t0 = state.tab, c0 = state.cat;
        catWait[catKey(t0, c0)] = 1;   // 首屏包还在路上, 界面要显示"正在加载该分类"
        // 后台预取的大分片立刻停: 不然 20KB 的分类包会被饿到十几秒(线上实测过)
        stopStream(t0);
        if (t0 === 'gal') {
          var man = state.manifest;
          var pk = man && man.galCatPack && man.galCatPack[c0];
          pauseWarmup();   // 用户点了分类: 立刻掐掉后台预热, 把 6 个 CDN 连接让给"被点的分类包"
          var after = function () {
            if (state.tab === t0 && state.cat === c0) pullForCat(t0, c0);
            else delete catWait[catKey(t0, c0)];
            resumeWarmupSoon(6000);   // 补分片先跑, 6s 后再续后台预热(不与补分片抢连接)
          };
          // 先等首屏包(单文件), 到了再补分片 —— 否则两个请求抢带宽, 首屏反而更慢
          if (pk) loadPack(t0, pk, 'gal', c0, after);
          else after();
        } else if (!state.done[t0]) {
          // 视频/文本等页签分片少(几个到几十个), 直接后台并发拉完, 边拉边刷
          streamChunks(t0, true);
        }
      } else if (!state.done[t0] && state.chunks[t0] < AUTO_CHUNKS) {
        // 回到「全部」: 后台预取可能被之前的分类点击掐过, 这里续上(只补到上限)
        streamChunks(t0);
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
  function cardHtml(p, idx) {
    var fb = p.fb || ('assets/img/cat-' + p.cat + '.jpg');
    var isVid = p.kind === 'video' && p.videoUrl;
    var flowVid = isVid && !p.cover;      // 没海报图: 视频本体当封面, 比例由视频自己决定
    var ar = '3 / 4';
    // 首屏前 8 张给高优先级并立即加载, 其余懒加载 —— 不然一屏金色渐变要等好几秒才出图
    var eager = (idx || 0) < 8;
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
      // 封面按真实宽高比撑开容器（加载完成覆写 --ar），所以图片是完整展示而不是裁切。
      // referrerpolicy: 有的图床(openimages)带第三方 referer 会 403, 必须去掉。
      // 后面的 cat-icon 是兜底占位: 图彻底加载不出来时 has-img 被移除, 露出渐变+图标。
      inner = '<img class="cover"' + (eager ? ' fetchpriority="high"' : ' loading="lazy"') +
        ' src="' + esc(coverUrl(p.cover)) + '"' +
        ' data-orig="' + esc(coverUrl(p.cover)) + '" referrerpolicy="no-referrer"' +
        ' onload="this.parentNode.classList.add(\'has-img\');' +
        'var r=this.naturalWidth/this.naturalHeight;' +
        'if(r>0.2&&r<5)this.parentNode.style.setProperty(\'--ar\',r.toFixed(3))"' +
        ' onerror="window.__imgFail&&window.__imgFail(this)" />' +
        '<span class="cat-icon">' + esc(p.catIcon || '✨') + '</span>';
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
    $('#grid').innerHTML = shown.map(function (p, i) { return cardHtml(p, i); }).join('');
    var ck = state.cat ? catKey(state.tab, state.cat) : '';
    // 还在补数据: 搜索没拉全, 或分类没拉全(gallery 按分片补, 其他页签整页拉)。
    // catWait 覆盖"点了分类、首屏包还在路上"那 1~2 秒, 不然界面会閃"没有匹配的提示词"。
    var stillLoading = !state.done[state.tab] &&
      (!!state.q.trim() || (!!state.cat && (state.tab !== 'gal' || !!catPulling[ck] || !!catWait[ck])));
    var empty = $('#empty');
    if (state.list.length) {
      empty.style.display = 'none';
    } else {
      empty.style.display = '';
      // 分类/搜索的数据可能还在后面的分片里 —— 说清楚"在加载", 别让用户以为分类是空的
      empty.innerHTML = stillLoading
        ? '<strong>正在加载该分类…</strong>数据还在后面的分片里，拉到就自动显示，稍等一下'
        : '<strong>没有匹配的提示词</strong>换个关键词或分类试试';
    }
    $('#loadMoreWrap').style.display = shown.length < state.list.length ? '' : 'none';
    // 条数要说老实: 分类 chip 上那个数是全量(比如 1335), 这里只是已经拉到的。
    // 分批拉取(首屏包 120 + 分片补到 240)是为了不把带宽占满, 差额标出来,
    // 想要更多可以点「加载更多」。不然用户会以为数据丢了。
    var catTotal = 0;
    if (state.cat && state.manifest && state.manifest.catCounts) {
      catTotal = (state.manifest.catCounts[state.tab] || {})[state.cat] || 0;
    }
    var tail = catTotal > state.list.length ? ' / 共 ' + catTotal + ' 条' : '';
    $('#resultCount').textContent = '（' + state.list.length + ' 条' + tail +
      (stillLoading ? '，加载中…' : '') + '）';
    var active = $('#categoriesScroll .chip.active');
    var label = active ? active.textContent.replace(/\d+$/, '').trim() : '全部';
    $('#listTitle').firstChild.nodeValue = state.q ? '搜索“' + state.q + '”' : label;
    $('#hint').textContent = state.onlyRefs
      ? '只看带风格参考图的图片条目（点开卡片可看参考图）'
      : (stillLoading && state.tab === 'gal'
        ? '⟳ 正在补充该分类的数据，数量会继续增长…'
        : (state.tab === 'gal'
          ? '图片提示词 · 点开卡片看完整提示词与风格参考'
          : (state.tab === 'video'
            ? (state.cat === 'hotvideo'
              ? '⚠️ 当前「热门视频」是 AI 生成的静音画面（没有声音）；想听原声 → 点回「全部」或 动作 / 口播 / 音乐MV 等分类（卡片右下角有 🔊）'
              : '✦ 开放精选视频优先展示；进画面自动静音循环，点开卡片可听原声（右下角 🔊 的是带原声的）')
            : '')));
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
    /* 案例类条目(如 H3 库)原帖未公开完整提示词时 body 为空, 这里给一段说明,
       避免弹窗正文区一片空白。desc 里带中文摘要与视频规格。 */
    if (!p.body) {
      return '<div class="prompt-text">' +
        '该案例原帖未公开完整提示词。' +
        (p.desc ? '<br><br>' + esc(p.desc) : '') +
        '</div>';
    }
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
        'data-orig="' + esc(coverUrl(p.cover)) + '" referrerpolicy="no-referrer" ' +
        'onerror="window.__imgFail&&window.__imgFail(this)" />';
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
            'data-orig="' + esc(coverUrl(refUrl)) + '" referrerpolicy="no-referrer" ' +
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
    h3: '正在加载开源 MiniMax H3…'
  };

  /* 分片清单：每个页签只装自己的分片。
     「开放精选」(oi_*) 排在最前 => 优先展示；后面跟原有分片。 */
  function shards(tab) {
    var m = state.manifest, out = [], i;
    // 外部图库(wf): 图片折进图库 / 视频折进视频页 / Vibe Coding 独立页签
    // 开源 MiniMax H3(h3): 独立页签, 行是 14 字段混合视频卡/图卡
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

  /* 自动后台预取的分片上限。
     首屏只需第 1 片即可渲染；再往前多备几片让"往下滚"顺滑。
     超过这个数就停下, 等用户点「加载更多」或搜索/筛选(需要全量)时再继续。
     好处: 不再一进站就把该页签全部分片拉完(oi_gal 15 片 + gal 79 片 ≈ 33MB),
     首屏带宽全留给图片, 而不是在后台空转下载用不到的数据。 */
  var AUTO_CHUNKS = 3;

  /* 并发拉片: 串行拉 95 个分片太慢(线上单分片 1~2 秒, 全量要好几分钟), 改成 4 路并发。
     结果先放 chunkBuf, 只有轮到 state.chunks[tab] 这一片才真正并入 pool —— 保证
     「加载更多」和首屏顺序不乱。 */
  var PARALLEL = 4;
  var inflight = {}, nextK = {}, chunkBuf = {}, applyTimer = {};
  // 正在飞的分片请求。用户一旦有了明确目标(点分类 / 搜索), 就要把它们掐掉:
  // oi_gal_0 单个就 444KB, 线上实测它一个把 22 秒的带宽全占了, 20KB 的
  // "分类首屏包"被饿到 16 秒才到 —— 用户看到的就是"点了分类一直 0 条"。
  var chunkAbort = {};
  // loadTab 首片请求的中断句柄(与 chunkAbort 分开: 首片有它自己的成功/失败语义)
  var firstAbort = {};

  /* 停掉某页签的后台预取请求。已下载并缓冲的片保留(下次 flushChunks 会并入),
     没下载完的片作废, 之后按需重新拉。 */
  function stopStream(tab) {
    var reqs = chunkAbort[tab];
    if (reqs) {
      Object.keys(reqs).forEach(function (k) {
        try { reqs[k].abort(); } catch (e) {}
        delete reqs[k];
      });
    }
    if (firstAbort[tab]) {
      try { firstAbort[tab].abort(); } catch (e) {}
      delete firstAbort[tab];
    }
    inflight[tab] = 0;
    nextK[tab] = state.chunks[tab];   // 从"下一个该并入的片"重新起算
  }

  function streamChunks(tab, force) {
    if (state.done[tab]) return;
    var list = shards(tab);
    var total = list.length;
    if (!total) { finishChunks(tab); return; }
    // 自动流水线到上限就暂停(force=true 时不受限, 供搜索/筛选/加载更多使用)
    var limit = force ? total : Math.min(total, AUTO_CHUNKS);
    if (!force && state.chunks[tab] >= AUTO_CHUNKS) return;
    if (nextK[tab] == null || nextK[tab] < state.chunks[tab]) nextK[tab] = state.chunks[tab];
    inflight[tab] = inflight[tab] || 0;
    chunkBuf[tab] = chunkBuf[tab] || {};
    chunkAbort[tab] = chunkAbort[tab] || {};

    while (inflight[tab] < PARALLEL && nextK[tab] < limit) {
      var k = nextK[tab]++;
      inflight[tab]++;
      var ctl = (window.AbortController) ? new AbortController() : null;
      if (ctl) chunkAbort[tab][k] = ctl;
      (function (kk, c) {
        var opts = c ? { signal: c.signal } : undefined;
        fetch(dataUrl(list[kk].f + '.json'), opts)
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
          .then(function (rows) {
            if (c && c.signal.aborted) return;         // 已被 stopStream 掐掉: 成果作废
            chunkBuf[tab][kk] = rows;
          })
          .catch(function (e) {
            if (c && c.signal.aborted) return;
            chunkBuf[tab][kk] = null;   // 单片失败: 跳过, 不堵后面的
          })
          .then(function () {
            if (c) {
              if (chunkAbort[tab]) delete chunkAbort[tab][kk];
              if (c.signal.aborted) return;           // inflight 已被 stopStream 清零
            }
            inflight[tab]--;
            if (flushChunks(tab, list)) scheduleApply(tab);
            if (state.done[tab]) return;
            if (nextK[tab] < limit) streamChunks(tab, force);
            else if (inflight[tab] === 0 && (limit >= total || force)) finishChunks(tab);
          });
      })(k, ctl);
    }
  }

  // 按分片号顺序并入 pool, 返回是否有新增
  function flushChunks(tab, list) {
    var buf = chunkBuf[tab] || (chunkBuf[tab] = {});
    var grew = false;
    while (buf[state.chunks[tab]] !== undefined) {
      var k = state.chunks[tab];
      var rows = buf[k];
      delete buf[k];
      if (rows && rows.length) {
        var d = list[k] || { k: tab };
        Array.prototype.push.apply(state[tab], rows.map(EXPAND[d.k] || EXPAND[tab]));
        grew = true;
      }
      state.chunks[tab] = k + 1;
    }
    if (grew) state.fails[tab] = 0;
    return grew;
  }

  /* 分类筛选时数据是"边拉边到"的: 每片到了要重绘一次, 否则用户一直看着 0 条。
     节流 800ms; 只在有分类/搜索条件时刷(纯「全部」浏览交给「加载更多」按钮)。 */
  function scheduleApply(tab) {
    if (state.tab !== tab) return;
    var filtered = !!(state.cat || state.q.trim());
    // 没有筛选时只在前几片补刷一次(让「全部」的条数不再卡在首片), 之后交给「加载更多」
    if (!filtered && state.chunks[tab] > AUTO_CHUNKS + 1) return;
    if (applyTimer[tab]) return;
    applyTimer[tab] = setTimeout(function () {
      applyTimer[tab] = 0;
      if (state.tab === tab) apply();
    }, 1200);
  }

  /* ---------- 分类专用拉取 ----------
     一个分类的条目只会落在同类分片里(中文分类在 gal_*, oi-* 在 oi_gal_*,
     wf-* 在 wf_image_*), 所以点分类时没必要把 95 个分片全拉一遍 —— 只拉
     相关的那一组, 6 路并发, 哪片先到先并入(筛选时顺序无所谓), 每片完成刷一次。
     这是"点开分类秒出数据"的关键: 拉的量从 ~34MB 降到 0.3~6MB。 */
  var catPulling = {}, catDone = {}, catToken = {};
  // catWait: 点了分类但"分类首屏包"还没到的那小段时间。这段时间 catPulling 还是 0,
  // 不靠它界面会说成"没有匹配的提示词", 用户就以为是分类坏了。
  var catWait = {};

  /* 首屏包: data/cp_all.json 与 data/cp_<hash>.json(每个分类前 120 条)。
     一个 60~300KB 的单文件, 比"拉 4~95 个分片"快一个数量级, 用来做
     首页和分类页的第一屏; 完整数据仍旧由分片渐进补。 */
  var packLoaded = {};
  // 分类首屏包的内存缓存: boot 后后台预热, 点分类时命中缓存零等待(消除 CDN 冷启动白屏)
  var catPackCache = {};
  function mergeRows(tab, rows, kind) {
    var seen = {};
    (state[tab] || []).forEach(function (p) { seen[p.id] = 1; });
    var add = [];
    rows.forEach(function (r) {
      var p = (EXPAND[kind] || EXPAND[tab])(r);
      if (!seen[p.id]) { seen[p.id] = 1; add.push(p); }
    });
    if (add.length) Array.prototype.push.apply(state[tab], add);
    return add.length;
  }
  function loadPack(tab, name, kind, cat, cb) {
    var key = tab + '|' + name;
    if (!name || packLoaded[key]) { if (cb) cb(); return; }
    // 复用预热缓存: 若 boot 已在后台拉过这个包(或正在拉), 直接共享同一个 promise, 不重复请求
    var pr = catPackCache[name];
    if (!pr) {
      pr = fetch(dataUrl(name + '.json'))
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .catch(function () { return null; });   // 失败返回 null, 下面清标记, 下次可重试
      catPackCache[name] = pr;
    }
    pr.then(function (rows) {
      if (!rows || !rows.length) { packLoaded[key] = 0; return; }   // 真拿到才继续, 失败留待重试
      var n = mergeRows(tab, rows, kind);
      if (!n) return;
      // 只有当前页签 + 当前分类还匹配时才重绘
      if (state.tab === tab && (cat == null || state.cat === cat)) apply();
    }).then(function () { if (cb) cb(); });
  }

  function catShardMatch(fname, cat) {
    if (/^oi-/.test(cat)) return /^oi_gal_/.test(fname);
    if (/^wf-/.test(cat)) return /^wf_image_/.test(fname);
    return /^gal_/.test(fname);
  }
  function catKey(tab, cat) { return tab + '|' + cat; }

  /* 一个分类最多补这么多个分片 / 这么多行就停手。
     每个中文分类都有 1000~2400 行、撒在全部 79 个 gal 分片里, 全拉 = 27MB。
     国内网络下一次点分类后台拉 27MB, 能把带宽占满好几分钟, 首屏包(20KB)和
     封面图全被饿死 —— 线上实测 20KB 的分类包被拖到 16 秒才到, 用户看到的就是
     "点了分类一直 0 条 / 不出图"。留一屏多的量(10 页), 想要更多用户会自己点
     「加载更多」, 那条路走的是 loadOneChunk -> streamChunks, 一样能补。 */
  var CAT_SHARD_MAX = 8;
  var CAT_ROW_MAX = 240;

  function pullForCat(tab, cat) {
    var key = catKey(tab, cat);
    if (state.done[tab] || catPulling[key] || catDone[key]) { delete catWait[key]; return; }
    catPulling[key] = 1;
    var myToken = catToken[tab] = (catToken[tab] || 0) + 1;
    // 已经按顺序并入的分片不用再拉(首屏包可能已经带来了它们的条目)
    var loaded = state.chunks[tab];
    var list = shards(tab).filter(function (d, idx) {
      return idx >= loaded && catShardMatch(d.f, cat);
    }).slice(0, CAT_SHARD_MAX);
    var seen = {};
    (state[tab] || []).forEach(function (p) { seen[p.id] = 1; });
    var i = 0, active = 0, stopped = false, got = 0, full = false;

    function settle() {
      catDone[key] = 1;
      catPulling[key] = 0;
      delete catWait[key];
      if (state.tab === tab && state.cat === cat) apply();
    }
    function next() {
      if (stopped || full) return;
      while (active < 3 && i < list.length) {
        var d = list[i++];
        active++;
        (function (dd) {
          fetch(dataUrl(dd.f + '.json'))
            .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
            .then(function (rows) {
              if (catToken[tab] !== myToken) {  // 用户又点了别的分类
                stopped = true; catPulling[key] = 0; delete catWait[key]; return;
              }
              var add = [];
              rows.forEach(function (r) {
                var p = (EXPAND[dd.k] || EXPAND[tab])(r);
                if (!seen[p.id]) { seen[p.id] = 1; add.push(p); }
              });
              if (add.length) {
                Array.prototype.push.apply(state[tab], add);
                got += add.length;
                scheduleApply(tab);
              }
            })
            .catch(function () {})
            .then(function () {
              active--;
              if (stopped) return;
              if (got >= CAT_ROW_MAX) { full = true; settle(); return; }
              if (active === 0 && i >= list.length) { settle(); return; }
              next();
            });
        })(d);
      }
    }
    if (!list.length) { settle(); return; }
    next();
  }

  function finishChunks(tab) {
    if (state.done[tab]) return;
    state.done[tab] = true;
    (state.chunkDone[tab] || []).forEach(function (fn) { try { fn(); } catch (e) {} });
    state.chunkDone[tab] = [];
    if (state.tab === tab) scheduleApply(tab);
  }

  // 等待某 tab 全部分片加载完成（用于搜索前确保结果完整）
  function ensureAll(tab) {
    return new Promise(function (resolve) {
      if (state.done[tab]) return resolve();
      streamChunks(tab, true);   // force: 绕过自动预取上限, 真的拉完
      var t = setInterval(function () {
        if (state.done[tab]) { clearInterval(t); resolve(); }
      }, 200);
      // 兜底: 网络太慢也别把界面锁死, 120 秒后先放行(后台仍在继续拉)
      setTimeout(function () { clearInterval(t); resolve(); }, 120000);
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
    // 首片(如 wf_image_0)自己也有一两 MB, 用户点分类时也得能让它把带宽交出来
    var ctl = (window.AbortController) ? new AbortController() : null;
    if (ctl) firstAbort[tab] = ctl;
    fetch(dataUrl(first.f + '.json'), ctl ? { signal: ctl.signal } : undefined)
      .then(function (r) { return r.json(); }).then(function (rows) {
      if (ctl) delete firstAbort[tab];
      var fresh = rows.map(EXPAND[first ? first.k : tab]);
      // 首屏包(cp_all)可能已经先到了: 不要覆盖, 只把新条目追加在后面
      var base = state[tab] || [];
      if (base.length) {
        var seen = {};
        base.forEach(function (p) { seen[p.id] = 1; });
        fresh = fresh.filter(function (p) { return !seen[p.id]; });
        state[tab] = base.concat(fresh);
      } else {
        state[tab] = fresh;
      }
      state.chunks[tab] = 1;
      state.loading[tab] = 0;
      if (!silent) busy(false);
      cb();
      // 仅画廊(gal)页签首屏不预取大分片: 首页只靠 cp_all, 把 6 个 CDN 连接全留给
      //  用户点分类时的小包(实测: 预取会占满管道, 分类包被排队 2.5s+ → 用户看到"0 条"以为坏了)。
      //  用户往下滚/点「加载更多」时才按需拉分片(此时没分类竞争, 带宽闲着)。
      //  其他页签(video/vibe/text/h3)分片少且无"分类包"竞争, 仍照常后台预取。
      if (tab !== 'gal') streamChunks(tab);   // 后台渐进拉取其余分片
    }).catch(function (e) {
      if (ctl && ctl.signal.aborted) {
        // 被 stopStream 掐掉(用户点了分类): 不算失败, 别弹 toast 吓人。
        // chunks 还是 0, 之后回这个页签会重新拉首片。
        state.loading[tab] = 0;
        if (!silent) busy(false);
        return;
      }
      if (ctl) delete firstAbort[tab];
      state.loading[tab] = 0;
      if (!silent) busy(false);
      toast('数据加载失败：请检查网络后重试');
      console.error(e);
    });
  }

  // 图片提示词页已下线(2026-10-13): 看图片请去「灵感画廊」。这里保留白名单,
  // 旧链接 (?tab=image) 会自动落回灵感画廊。
  var TABS = ['gal', 'video', 'h3', 'text', 'vibe'];

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
    stopStream(state.tab);   // 旧页签的后台预取别跟新页签抢带宽
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
    var afterTab = function () {
      buildCategories();
      // 视频页默认「全部」: 开放精选(oi)视频排在最前; 旧的热门静音视频在分类里按需筛
      apply();
    };
    if (tab === 'gal' && state.manifest && state.manifest.galAllPack) {
      loadPack('gal', state.manifest.galAllPack, 'gal', null, function () { loadTab(tab, afterTab); });
    } else {
      loadTab(tab, afterTab);
    }
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
        ' src="' + esc(coverUrl(x.cover)) + '" data-orig="' + esc(coverUrl(x.cover)) + '"' +
        ' referrerpolicy="no-referrer" alt=""' +
        ' onerror="window.__imgFail&&window.__imgFail(this)" />' +
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

  // 后台预热分类首屏包: 触发 CDN 边缘缓存, 用户点分类时命中缓存零等待。
  // 关键1 并发限量 2 —— 37 个包各 5~22s(冷), 一次拉太猛立刻占满 6 连接,
  //   用户正点的小分类包(17KB)被饿死在队尾 → "点分类 0 条"(本文件反复出现的病根)。
  // 关键2 全程可被"点分类"瞬间掐断(pauseWarmup) —— 用户一点分类就 abort 掉在飞的预热,
  //   把 6 个连接让给"被点的分类包 + 补分片", 冷启动也能尽快拿到首屏; 拉完再 resume 续预热。
  // 关键3 只有成功拿到 rows 才写 catPackCache(resolved promise); 被掐/失败/空包一律不写,
  //   让点击方自己去拉 —— 绝不遗留一个永远 null 的 promise 把该分类卡死在 0 条。
  var warmCtl = null, warmResumeT = null, warmGen = 0;
  function pauseWarmup() {
    if (warmCtl) { try { warmCtl.abort(); } catch (e) {} warmCtl = null; }
    if (warmResumeT) { clearTimeout(warmResumeT); warmResumeT = null; }
  }
  function resumeWarmupSoon(ms) {
    if (warmResumeT) clearTimeout(warmResumeT);
    warmResumeT = setTimeout(function () { warmResumeT = null; if (state.manifest) warmupCatPacks(state.manifest); }, ms || 5000);
  }
  function warmupCatPacks(m) {
    var cp = (m && m.galCatPack) || {};
    var keys = Object.keys(cp).filter(function (k) { return cp[k] && !catPackCache[cp[k]]; });
    if (!keys.length) return;
    pauseWarmup();
    var i = 0, active = 0, MAX = 2, gen = ++warmGen;
    var ctl = (window.AbortController) ? new AbortController() : null;
    warmCtl = ctl;
    var sig = ctl ? ctl.signal : undefined;
    function next() {
      if (gen !== warmGen) return;   // 已被更新的预热/暂停顶替: 停手
      while (active < MAX && i < keys.length) {
        var nm = cp[keys[i++]];
        active++;
        (function (nm2) {
          fetch(dataUrl(nm2 + '.json'), sig ? { signal: sig } : undefined)
            .then(function (r) { return r.ok ? r.json() : null; })
            .catch(function (e) { if (e && e.name === 'AbortError') return undefined; return null; })
            .then(function (rows) {
              // AbortError -> undefined: 不写缓存, 让点击方自己拉
              if (Array.isArray(rows) && rows.length && !catPackCache[nm2]) catPackCache[nm2] = Promise.resolve(rows);
              active--;
              if (gen === warmGen) next();
            });
        })(nm);
      }
    }
    next();
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
      // 分类栏只依赖 manifest, manifest 一到立刻渲染 —— 不再等 cp_all/首片, 消除首屏白屏(用户以为页面坏了)
      buildCategories();
      var afterTab = function () { apply(); };
      if (start === 'gal' && m.galAllPack) {
        // 首屏: 拉 cp_all(即时首屏) + gal_0 首片(兜底数据, 点分类时即使分类包未到也有图)。
        // gal_0 仅占 1 个 CDN 连接(不会饿死分类包); gal 页签不再后台预取后续大分片。
        loadPack('gal', m.galAllPack, 'gal', null, function () {
          loadTab(start, afterTab);   // 拉 gal_0 首片作兜底
          setTimeout(function () { warmupCatPacks(m); }, 1200);   // 首屏后再预热(并发3, 不抢交互)
        });
      } else {
        loadTab(start, afterTab);    // 其他页签分片少, 仍取第 0 片 + 后台渐进拉取
        setTimeout(function () { warmupCatPacks(m); }, 1200);
      }
    }).catch(function (e) {
      $('#grid').innerHTML = '<div class="empty"><strong>数据加载失败</strong>' +
        '请刷新页面重试。</div>';
      console.error(e);
    });
  }

  boot();
})();

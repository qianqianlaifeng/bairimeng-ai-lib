# -*- coding: utf-8 -*-
"""
分类重整 v7（GPT 合并 + 人像洁净加强 + 人像总集首屏包）
======================================================
历史版本见 git；要点：
  v6: GPT 系列并成 "GPT Image"；人像三桶分工；新增「人像（全部）」首屏包
  v7: 分类判定加强（用户反馈"人像写真里还有神兽/动物/商品，人像人物里还有插画"）
      人像三个桶重新定义：
        人像写真 = 写实真人照片（标题/提示词都指向"照片/写实"）
        人像动漫 = 一切非写实（动漫/插画/绘画/3D/粘土/拼贴/超现实/雕塑…）
        人像人物 = 认不出风格的（保留兜底，不再混进大量插画）
      KOOK 不再在数据层合并（保留 kook-yaoguang / kook-rumengsihuan 两个原始键），
      由前端把两个键折叠成一个「KOOK」芯片 + 子筛选（全部 / 瑶光 / 如梦似幻）。

本脚本一次做完：
  A. 合并 GPT 系列分类 -> 单一 "GPT Image"（oi-/wf-/kook- 三种来源全并）
  B. 人像纠错：
       - 非人物主体（动物/神兽/商品/设计/局部）-> 归位到对应分类
       - 非写实风格（画/3D/合成/超现实）-> 人像动漫
       - 只有"照片/写实"信号 -> 人像写真
  C. 重建所有分类首屏包（cp_*.json），人像类按"分类对口"的纯度分排序
  D. 「人像（全部）」首屏包 cp_portrait_all.json（跨全部分类，给性别筛选用）
  E. 更新 manifest（galCats / catCounts.gal / galCatPack / portraitAll* / totalCats）
     与 DATA_VER

用法：
  python tools/reorg_cats_v6.py            # 干跑，只打印
  python tools/reorg_cats_v6.py --apply    # 写盘
"""
import json, os, sys, re, glob, hashlib, shutil
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
APPLY = '--apply' in sys.argv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import purify_portrait_v4 as V4            # noqa: E402
from purify_portrait_v4 import portrait_score, has_person_subject, _s, FACE_RELATED  # noqa: E402
# 「全部」首屏按发布日期倒序——和 app.js itemDate / build_catpack 保持同一套规则，
# 防止每日刷新时这里把 cp_all 覆盖回来源顺序(旧的 5 月数据排在 11 月前面)。
from build_catpack import _item_date as _item_date  # noqa: E402

PORTRAIT_CATS = ('人像写真', '人像人物', '人像动漫')
# KOOK 两个栏目的显示名（数据里的键在每日同步脚本里固定）
KOOK_LABELS = {'kook-yaoguang': '瑶光', 'kook-rumengsihuan': '如梦似幻'}


def is_kook_key(k):
    k = str(k or '')
    return k.startswith('kook-') and k != 'kook-gpt-image'

# ---------------- A. GPT 合并 ----------------
GPT_CAT = 'GPT Image'
GPT_ICON = '🤖'
GPT_KEYS = {
    'oi-gpt-image', 'oi-gpt-image-2', 'oi-gpt-image-2-5',
    'wf-m-gpt-image-2', 'wf-m-gpt-image-2-5', 'wf-m-gpt-image-2-6',
    'wf-m-gpt-6-astra', 'kook-gpt-image',
}

# ---------------- B0. 修正 v4 的"人物主语" ----------------
# 原 PERSON_SUBJECT 把「肖像 / 人像 / 自拍 / 人物」也算成人物主语，于是
# "边境牧羊犬的肖像插图""神兽青鸟的肖像"一路过关（先判定有人物主语 -> 直接保留）。
# 这几个词是画风/体裁词，不是人，必须剔出去，交给后面的动物/商品规则处理。
V4.PERSON_SUBJECT = re.compile(
    r'女人|男人|女孩|男孩|女性|男性|少女|少年|女士|先生|模特|新娘|新郎|老人|小孩|儿童|婴儿|'
    r'姑娘|小伙|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|她|他们|'
    r'女子|男子|女生|男生|女孩儿|男孩儿|闺女|少爷|小姐|夫妇|情侣|母女|父子|人类|人身|'
    r'将军|牧童|骑士|法师|巫师|忍者|武士|乐手|学生|白领|大叔|大爷|老太|小伙|姑娘|夫人|'
    r'woman|women|man|men|girl|boy|female|male|model|lady|gentleman|child|baby|teenager|'
    r'brunette|blonde|\bshe\b|\bhe\b',
    re.I
)
# 动物/神兽/拟人实体（用于"XX 的肖像/自拍/人像"这种主语是物的伪装）
# 动物/神兽/非人实体：不用 v4 原表的单字（"鹅蛋脸"会命中"鹅"、"熊熊燃烧"会命中"熊"），
# 单字一律加否定环视，只匹配真正指动物的用法。
V4.CREATURE = re.compile(
    r'虎斑猫|北极熊|浣熊|牧羊犬|雪纳瑞|西伯利亚猫|花猫|蜂鸟|白鹅|乌鸦|老鼠|蝾螈|考拉|树懒|'
    r'猫头鹰|恐龙|海豚|鲨鱼|老虎|狮子|熊猫|企鹅|松鼠|狐狸|兔子|哈士奇|柯基|金毛|孔雀|'
    r'天鹅|仙鹤|白鹭|猎鹰|雄鹰|飞鹰|神兽|青鸟|凤凰|朱雀|玄武|麒麟|貔貅|饕餮|瑞兽|'
    r'地精|怪物|怪兽|恶魔|机器人|雕像|雕塑|宝马|汽车|香水瓶|花瓶|'
    r'猫(?!眼|尾|耳)|狗(?!牙|粮|尾|带)|鹅(?!蛋)|(?<!熊)熊(?!熊)|马(?!尾|卡龙|赛克|甲)|'
    r'牛(?!油|排|仔|奶)|羊(?!绒|毛)|鸡(?!蛋|尾|汤)|鸭(?!蛋)|兔(?!唇)|狼(?!狈)|鹿(?!角)',
    re.I
)
_np = V4.NONPERSON_SUBJ.pattern
_np = _np.replace(r'(猎豹|', r'(神兽|青鸟|凤凰|朱雀|玄武|麒麟|貔貅|饕餮|瑞兽|猎鹰|雄鹰|白鹭|孔雀|猎豹|')
_np = _np.replace(r'(?:一张|一个|一只|一幅|一座|一辆|', r'(?:一张|一个|一只|一幅|一座|一辆|一尊|一匹|一头|一群|一具|')
V4.NONPERSON_SUBJ = re.compile(_np, re.I)

# ---------------- B. 风格信号 ----------------
# 非写实：绘画 / 二次元 / 3D / 手办 / 合成艺术 全部算一挂 -> 人像动漫
ART = re.compile(
    r'动漫|卡通|二次元|漫画|anime|manga|cartoon|动画|插画|插图|illustration|绘本|漫画风|'
    r'3d渲染|3d render|\bc4d\b|blender|octane|虚幻引擎|unreal engine|三维模型|3d模型|'
    r'粘土|黏土|毛毡|像素|pixel art|低多边形|low poly|厚涂|板绘|赛璐璐|cel.?shad|'
    r'布偶|玩偶|手办|盲盒|皮克斯|pixar|迪士尼|disney|吉卜力|ghibli|泡泡玛特|乐高|lego|'
    r'拟人化|anthropomorph|cyborg|半机械人|怪物|怪兽|monster|goblin|地精|恶魔|'
    r'超现实主义|超现实(?!写实)|surreal|故障艺术|glitch|双重曝光|double exposure|'
    r'数字绘画|digital painting|数字艺术|digital art|拼贴|拼贴画|collage|'
    r'油画|水彩|版画|木雕|雕塑|雕像|剪纸|'
    r'粉笔|粉彩|蜡笔|素描|速写|涂鸦|手绘|绘制|绘画|图画|画作|水墨|国画|壁画|'
    r'concept art|概念艺术|artwork|painting|drawing|sketch|vector art|矢量图|'
    r'巨物|微缩.{0,8}(人物|人|世界|场景)|极小的人',
    re.I
)
# 明确写实信号（只在标题里判；正文里"照片"常出现在否定/对比里，容易误判）
PURE_REAL = re.compile(
    r'照片|摄影|写真|photograph|photo|realistic|写实|实拍|单反|相机拍摄|镜头|'
    r'肖像照|自拍|selfie|85mm|50mm|35mm|f/1\.4|景深|胶片', re.I
)
# 神话/瑞兽：这类标题常在中间写"XX神兽的形象"，主语不在开头，单独补一条
MYTH = re.compile(r'神兽|饕餮|貔貅|麒麟|青鸟|凤凰|朱雀|玄武|瑞兽|仙鹤|白鹭', re.I)
# 商品/包装主体（没有任何人物主语时才算商品）
PRODUCT = re.compile(
    r'香水|香薰|沐浴露|洗发水|护发|唇釉|口红|面霜|精华液|粉底|乳液|面膜|身体乳|'
    r'瓶身|包装设计|产品图|商品图|礼盒|蜡烛|马克杯|水杯|保温杯|香水瓶', re.I
)


def strip_negative(prompt):
    t = _s(prompt)
    for pat in [r'--no\b', r'\bnegative\s*prompt\b', r'负面提示词', r'负面词']:
        m = re.search(pat, t, re.I)
        if m:
            t = t[:m.start()]
    return t


def classify_v7(title, prompt):
    """非人物主体判定：先走 v4 的保守规则，再补商品/神兽。"""
    nc, why = V4.strict_classify(title, prompt)
    if nc:
        return nc, why
    head = _s(title)[:44]
    # 动物/神兽出现在标题前部、且没有人物主语 -> 不是人像
    # （"中国古代神话故事《山海经》的中神兽饕餮的形象"这种，主语不在开头，
    #   v4 的 ^ 锚定匹配不到，这里补一刀）
    m = MYTH.search(head[:36])
    if m and not has_person_subject(head):
        return V4.nonperson_target(m.group(0))
    m = PRODUCT.search(head)
    if m and not has_person_subject(head):
        return '产品电商', '商品主体:' + m.group(0)
    return None, ''


def style_fix(title, prompt, cur):
    """写实 / 非写实纠错：返回 (新分类, 原因) 或 (None, '')。

    只看标题，不看正文：正文里"3D/水彩/照片"这类词在写实提示词里也常出现
    （"真人向写实…设定图，3D 渲染参考"），拿正文判会把写实照片误判成动漫。
    """
    head = _s(title)[:80]
    art_head = ART.search(head)
    real_head = PURE_REAL.search(head)
    # 标题同时写了"照片/写实"和画风词 -> 风格矛盾，保持原样不动
    if art_head and real_head:
        return None, ''
    if cur in ('人像写真', '人像人物'):
        if art_head:
            return '人像动漫', '非写实:' + art_head.group(0)[:10]
        # 人像人物本来就是"风格不明"的兜底桶：标题没线索时，用提示词正文兜一下
        # （"…有很多电视的背景是破碎的屏幕，还有数字插图"这种，其实是插画）
        if cur == '人像人物' and not real_head:
            b = strip_negative(prompt)[:180]
            # 正文自己写着"摄影/照片/写实"的（"超现实摄影，光线追踪"）就别动
            if not PURE_REAL.search(b):
                m = ART.search(b)
                if m:
                    return '人像动漫', '正文非写实:' + m.group(0)[:8]
        # 只有写实信号、没有任何画风信号 -> 写真
        if cur == '人像人物' and real_head and has_person_subject(head):
            return '人像写真', '写实照片'
    elif cur == '人像动漫':
        if (not art_head) and real_head and has_person_subject(head):
            return '人像写真', '纯写实照片'
    return None, ''


def score_v6(r):
    """分类对口的人像纯度分：写真看写实感，动漫看画风信号。"""
    t, p, cat = _s(r[1]), _s(r[2])[:200], _s(r[3])
    s = portrait_score(r)
    head = t[:70]
    art = bool(ART.search(head))
    real = bool(PURE_REAL.search(head))
    if cat == '人像写真':
        if art:
            s -= 30
        if real:
            s += 5
        if FACE_RELATED.search(head[:40]):
            s += 2
    elif cat == '人像动漫':
        if art:
            s += 6
        if re.search(r'动漫|插画|卡通|二次元|anime|manga|illustration|3D|CG', head, re.I):
            s += 4
    elif cat == '人像人物':
        if art:
            s -= 8
    else:
        if not has_person_subject(t[:34]):
            s -= 6
    return s


def score_all(r):
    """「人像（全部）」用中性分：只看"是不是一个明确的人物"，不分画风。"""
    t = _s(r[1])
    head = t[:70]
    s = portrait_score(r)
    if has_person_subject(t[:34]):
        s += 4
    if FACE_RELATED.search(head[:40]):
        s += 3
    if PURE_REAL.search(head):
        s += 2
    if not has_person_subject(t[:34]):
        s -= 4
    return s


# 标题里"明确是人"的词（用于跨分类的人像总集）
PERSON_WORD = re.compile(
    r'女人|男人|女孩|男孩|女性|男性|少女|少年|女士|先生|模特|新娘|新郎|老人|小孩|儿童|婴儿|'
    r'姑娘|小伙|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|人物|人像|肖像|自拍|'
    r'美女|帅哥|女神|少女感|小姐姐|老板娘|护士|教师|老师|医生|警察|军人|白领|学生|'
    r'woman|women|man\b|men\b|girl|boy|female|male|model|lady|gentleman|'
    r'portrait|selfie|headshot|person|people|human',
    re.I
)


def slug(cat):
    return 'cp_' + hashlib.md5(cat.encode('utf-8')).hexdigest()[:10]


def shard_files():
    files = []
    for prefix in ('jimeng_gal', 'kook_image', 'wf_image', 'oi_gal', 'gal'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp):
                break
            files.append(fp)
            i += 1
    return files


def load_shards():
    """必须按 app.js shards('gal') 的顺序：jimeng_gal -> kook_image -> wf_image -> oi_gal -> gal。"""
    out = []
    for fp in shard_files():
        out.extend(json.load(open(fp, encoding='utf-8')))
    return out


def is_portrait_like(r):
    """跨分类"这算不算人像"：人像三类全收；其他类看标题有没有明确人物主语。"""
    cat = _s(r[3])
    if cat in PORTRAIT_CATS:
        return True
    return bool(PERSON_WORD.search(_s(r[1])[:40]))


def main():
    files = shard_files()
    if not files:
        sys.exit('!! 没找到 gal 分片')

    if APPLY:
        bak = os.path.join(ROOT, '_backup_pre_reorg_v6')
        os.makedirs(bak, exist_ok=True)
        for f in files + glob.glob(os.path.join(DATA, 'cp_*.json')) + [os.path.join(DATA, 'manifest.json')]:
            shutil.copy2(f, os.path.join(bak, os.path.basename(f)))
        print('已备份 ->', bak)

    # ---------- A+B：改分片里的分类 ----------
    moved = Counter()
    samples = []
    gpt_n = 0
    for fp in files:
        d = json.load(open(fp, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) < 6:
                continue
            cat = _s(r[3])
            if cat != GPT_CAT and (cat in GPT_KEYS or 'gpt' in cat.lower()):
                r[3] = GPT_CAT
                gpt_n += 1
                dirty = True
                continue
            if cat in PORTRAIT_CATS:
                nc, why = classify_v7(r[1], r[2])
                if not nc:
                    nc, why = style_fix(r[1], r[2], cat)
                if nc and nc != cat:
                    moved[(cat, nc, why.split(':')[0])] += 1
                    if len(samples) < 400:
                        samples.append((cat, nc, why, _s(r[1])[:56]))
                    r[3] = nc
                    dirty = True
        if dirty and APPLY:
            with open(fp, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    print('GPT 系列合并 -> %s : %d 条' % (GPT_CAT, gpt_n))
    print('人像类改判:', sum(moved.values()), '条')
    for (a, b, why), n in moved.most_common():
        print('  %5d  %s -> %s  (%s)' % (n, a, b, why))

    by_reason = {}
    for a, b, why, t in samples:
        by_reason.setdefault((a, b, why.split(':')[0]), []).append(t)
    for k in list(by_reason)[:8]:
        print('\n--- 抽样 %s -> %s (%s) ---' % k)
        for t in by_reason[k][:6]:
            print('   ', t)

    # ---------- C/D：重建首屏包 ----------
    rows = load_shards()
    by_cat = {}
    for r in rows:
        if len(r) > 3:
            by_cat.setdefault(_s(r[3]), []).append(r)

    pack = {}
    total_pack_rows = 0
    for cat, items in by_cat.items():
        name = slug(cat)
        ranked = sorted(items, key=score_v6, reverse=True)[:150] if cat in PORTRAIT_CATS else items[:120]
        pack[cat] = name
        total_pack_rows += len(ranked)
        if APPLY:
            with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as fh:
                json.dump(ranked, fh, ensure_ascii=False, separators=(',', ':'))

    all_sorted = sorted(rows, key=_item_date, reverse=True)
    if APPLY:
        with open(os.path.join(DATA, 'cp_all.json'), 'w', encoding='utf-8') as fh:
            json.dump(all_sorted[:120], fh, ensure_ascii=False, separators=(',', ':'))

    # 「人像（全部）」首屏包：跨全部分类抽人像，按桶轮流取，首屏风格混杂不会一边倒
    cand = [r for r in rows if len(r) > 3 and is_portrait_like(r)]
    buckets = {'人像写真': [], '人像人物': [], '人像动漫': [], '其他': []}
    for r in cand:
        k = _s(r[3])
        buckets[k if k in buckets else '其他'].append(r)
    for k in buckets:
        buckets[k].sort(key=score_all, reverse=True)
    order = [('人像写真', 2), ('人像动漫', 1), ('人像人物', 1), ('其他', 1)]
    cand_ranked, idx = [], {k: 0 for k in buckets}
    while len(cand_ranked) < 720:
        grew = False
        for k, take in order:
            for _ in range(take):
                i = idx[k]
                if i < len(buckets[k]) and len(cand_ranked) < 720:
                    cand_ranked.append(buckets[k][i])
                    idx[k] = i + 1
                    grew = True
        if not grew:
            break
    if APPLY:
        with open(os.path.join(DATA, 'cp_portrait_all.json'), 'w', encoding='utf-8') as fh:
            json.dump(cand_ranked, fh, ensure_ascii=False, separators=(',', ':'))
    pack['人像全部'] = 'cp_portrait_all'

    # ---------- E：manifest ----------
    mp = os.path.join(DATA, 'manifest.json')
    man = json.load(open(mp, encoding='utf-8'))
    cats_meta = dict(man.get('galCats') or {})
    for k in list(cats_meta.keys()):
        if k != GPT_CAT and (k in GPT_KEYS or 'gpt' in k.lower()):
            del cats_meta[k]
    cats_meta[GPT_CAT] = [GPT_CAT, GPT_ICON]

    cnt = Counter(_s(r[3]) for r in rows if len(r) > 3)

    # galCats 与真实分片对齐：清掉已经没有条目的旧键（如合并前的 kook），
    # 补回分片里有、但 meta 里缺的键（每日刷新后 build_kook 会重写，这里做兜底）
    for k in list(cats_meta.keys()):
        if cnt.get(k, 0) <= 0:
            del cats_meta[k]
    def _fallback_label(k):
        ks = str(k)
        if ks.startswith('jimeng-'):
            name = ks.split('-', 1)[-1]
            icon = {'平面设计': '🆕', '电商': '🛍️', '动画动漫': '🎬', '影视作品': '🎞️'}.get(name, '✨')
            return ['即梦·' + name, icon]
        return [KOOK_LABELS.get(k, k), '🎨' if is_kook_key(k) else '✨']
    for k in cnt:
        if k not in cats_meta:
            cats_meta[k] = _fallback_label(k)
    man['galCats'] = cats_meta
    man.setdefault('catCounts', {})['gal'] = dict(cnt)
    man['galCatPack'] = pack
    man['galAllPack'] = 'cp_all'
    man['portraitAllPack'] = 'cp_portrait_all'
    man['portraitAllCount'] = len(cand)
    man['portraitCats'] = list(PORTRAIT_CATS)
    man['totalCats'] = (len(man.get('cats', {})) + len(man.get('imageCats', {})) +
                        len(man.get('videoCats', {})) + len(man.get('galCats', {})))
    man['uiVersion'] = '2026-11-20-cat-reorg-v7'
    sig = hashlib.md5()
    for k in sorted(pack.keys()):
        sig.update(('%s|%s' % (k, pack[k])).encode('utf-8'))
    sig.update(json.dumps(cand_ranked, ensure_ascii=False).encode('utf-8'))
    sig.update(json.dumps(all_sorted[:120], ensure_ascii=False).encode('utf-8'))
    man['packsSig'] = sig.hexdigest()[:8]
    if APPLY:
        with open(mp, 'w', encoding='utf-8') as fh:
            json.dump(man, fh, ensure_ascii=False, separators=(',', ':'))

    if APPLY:
        keep = set(pack.values()) | {'cp_all'}
        removed = 0
        for f in glob.glob(os.path.join(DATA, 'cp_*.json')):
            if os.path.basename(f)[:-5] not in keep:
                os.remove(f)
                removed += 1
        if removed:
            print('清理废弃首屏包:', removed, '个')

    # ---------- 自检 ----------
    print('\n=== 分类计数（前 14）===')
    for k, v in cnt.most_common(14):
        print('  %-16s %6d' % (k, v))
    print('人像三类: 写真=%d 人物=%d 动漫=%d | 人像（全部）候选=%d | GPT=%d'
          % (cnt['人像写真'], cnt['人像人物'], cnt['人像动漫'], len(cand), cnt[GPT_CAT]))
    print('首屏包: %d 个分类 + 全部 + 人像全部' % len(by_cat))

    for cat in PORTRAIT_CATS:
        top = sorted(by_cat.get(cat, []), key=score_v6, reverse=True)[:150]
        hd = [_s(r[1])[:70] for r in top]
        art = sum(1 for h in hd if ART.search(h))
        print('\n=== %s 首屏（%d 条）非写实信号=%d ===' % (cat, len(top), art))
        for r in top[:8]:
            print('  [%3d] %s' % (score_v6(r), _s(r[1])[:56]))

    if not APPLY:
        print('\n[DRY-RUN] 未写盘。加 --apply 生效。')
        return

    ver = hashlib.md5(open(mp, 'rb').read()).hexdigest()[:8]
    cp = os.path.join(ROOT, 'assets', 'js', 'config.js')
    s = open(cp, encoding='utf-8').read()
    s = re.sub(r"DATA_VER: '[^']*'", "DATA_VER: '%s'" % ver, s)
    open(cp, 'w', encoding='utf-8').write(s)
    print('\nDATA_VER =', ver)


if __name__ == '__main__':
    main()

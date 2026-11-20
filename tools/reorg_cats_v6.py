# -*- coding: utf-8 -*-
"""
分类重整 v6（GPT 合并 + 人像洁净 + 人像总集首屏包）
====================================================
用户反馈三件事：
  1) 人像写真里还有"超现实合成艺术"这类不属于该分类的图；
  2) 分类拆细之后每个类人变少了，希望"人像"能跨全部分类一起筛男女；
  3) GPT 系列（GPT Image / GPT Image 2 / 2.5 / 2.6 / GPT-6 Astra …）被拆成一堆
     分类，要求"GPT 的跟 GPT 放一起"。

本脚本一次做完：
  A. 合并 GPT 系列分类 -> 单一 "GPT Image"（oi-/wf-/kook- 三种来源全并）
  B. 人像风格纠错（在 v4/v5 基础上加强）：
       人像写真只留写实照片；超现实/插画/3D/黏土/拼贴/巨物+微缩 等 -> 人像动漫
       人像动漫里纯写实照片 -> 人像写真
  C. 重建所有分类首屏包（cp_*.json），人像类按"分类对口"的纯度分排序
  D. 新增「人像（全部）」首屏包 cp_portrait_all.json —— 跨全部 42 个分类抽取
     标题里明确有人物主语的条目（约 1.3 万条），供前端性别筛选用
  E. 更新 manifest（galCats / catCounts.gal / galCatPack / portraitAll* / totalCats）
     与 DATA_VER、index.html 的 ?v=

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
from purify_portrait_v4 import (          # noqa: E402
    strict_classify, portrait_score, has_person_subject, _s,
    FACE_RELATED, creature_disguised,
)

PORTRAIT_CATS = ('人像写真', '人像人物', '人像动漫')

# ---------------- A. GPT 合并 ----------------
GPT_CAT = 'GPT Image'
GPT_ICON = '🤖'
GPT_KEYS = {
    'oi-gpt-image', 'oi-gpt-image-2', 'oi-gpt-image-2-5',
    'wf-m-gpt-image-2', 'wf-m-gpt-image-2-5', 'wf-m-gpt-image-2-6',
    'wf-m-gpt-6-astra', 'kook-gpt-image',
}

# ---------------- B. 风格信号 ----------------
# 二次元 / 插画 / 3D / 手办这一挂 -> 人像动漫
ART_ANIME = re.compile(
    r'动漫|卡通|二次元|漫画|anime|manga|cartoon|动画|插画|illustration|绘本|'
    r'3d渲染|3d render|\bc4d\b|blender|octane|虚幻引擎|unreal engine|三维模型|3d模型|'
    r'粘土|黏土|毛毡|像素|pixel art|低多边形|low poly|厚涂|板绘|赛璐璐|cel.?shad|'
    r'布偶|玩偶|手办|盲盒|皮克斯|pixar|迪士尼|disney|吉卜力|ghibli|泡泡玛特|乐高|lego|'
    r'拟人化|anthropomorph|cyborg|半机械人|怪物|怪兽|monster|goblin|地精|恶魔',
    re.I
)
# 艺术 / 合成 / 超现实这一挂 -> 人像人物（风格不明桶，不再挤进写真）
ART_OTHER = re.compile(
    r'超现实主义|超现实(?!写实)|surreal|故障艺术|glitch|双重曝光|double exposure|'
    r'数字绘画|digital painting|数字艺术|digital art|拼贴|拼贴画|collage|'
    r'油画|水彩|版画|木雕|雕塑|雕像|剪纸|'
    r'纪录片风格插画|概念艺术|concept art',
    re.I
)
# 尺度异常 / 合成感很强的构图（巨物+微缩人物这类）
SCALE_WEIRD = re.compile(
    r'巨大的.{0,12}(头部|脑袋|脸|面孔|身体|手|脚)|'
    r'微缩.{0,8}(人物|人|世界|场景)|巨人|极小的人|'
    r'站在.{0,8}脚手架上|在.{0,8}头发上|漂浮在空|悬浮在空|'
    r'头发里.{0,8}(人|工人|发型师)|头上.{0,6}站着',
    re.I
)
# 纯写实照片信号（把动漫类里混进来的写实图纠回去）
PURE_REAL = re.compile(
    r'照片|摄影|写真|photograph|photo|realistic|写实|实拍|单反|相机拍摄|镜头|'
    r'肖像照|自拍|selfie|85mm|50mm|f/1\.4|景深', re.I
)
# 标题里"明确是人"的词（用于跨分类的人像总集）
PERSON_WORD = re.compile(
    r'女人|男人|女孩|男孩|女性|男性|少女|少年|女士|先生|模特|新娘|新郎|老人|小孩|儿童|婴儿|'
    r'姑娘|小伙|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|人物|人像|肖像|自拍|'
    r'美女|帅哥|女神|少女感|小姐姐|老板娘|护士|教师|老师|医生|警察|军人|白领|学生|'
    r'woman|women|man\b|men\b|girl|boy|female|male|model|lady|gentleman|'
    r'portrait|selfie|headshot|person|people|human',
    re.I
)


def style_fix(title, prompt, cur):
    """写实/非写实风格纠错：返回 (新分类, 原因) 或 (None, '')。"""
    t = _s(title)
    head = t[:70]
    hyper_only = bool(re.search(r'超写实|hyperrealistic', head, re.I)) and \
        not re.search(r'超现实(?!写实)|surreal', head, re.I)
    m_anime = ART_ANIME.search(head)
    m_other = ART_OTHER.search(head) or SCALE_WEIRD.search(head)
    if cur == '人像写真':
        if hyper_only:
            return None, ''
        if m_anime:
            return '人像动漫', '二次元/3D:' + m_anime.group(0)[:12]
        if m_other:
            return '人像人物', '艺术合成:' + m_other.group(0)[:12]
    elif cur == '人像人物':
        if m_anime:
            return '人像动漫', '二次元/3D:' + m_anime.group(0)[:12]
    elif cur == '人像动漫':
        if (not m_anime) and (not m_other) and PURE_REAL.search(head) and has_person_subject(head):
            return '人像写真', '纯写实照片'
    return None, ''


def score_v6(r):
    """分类对口的人像纯度分：写真看写实感，动漫看画风信号。"""
    t, p, cat = _s(r[1]), _s(r[2])[:200], _s(r[3])
    s = portrait_score(r)
    head = t[:70]
    anime = bool(ART_ANIME.search(head))
    art = anime or bool(ART_OTHER.search(head) or SCALE_WEIRD.search(head))
    if cat == '人像写真':
        if art:
            s -= 30
        if re.search(r'照片|摄影|写真|实拍|photograph|photo\b|realistic', head, re.I):
            s += 5
        if FACE_RELATED.search(head[:40]):
            s += 2
    elif cat == '人像动漫':
        if anime:
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
    """「人像（全部）」用中性分：只看"是不是一个明确的人物"，不分画风。
    这样首屏是写实照片和二次元交替出现，不会一屏全是动漫。"""
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


def slug(cat):
    return 'cp_' + hashlib.md5(cat.encode('utf-8')).hexdigest()[:10]


def load_shards():
    """必须按 app.js shards('gal') 的顺序：kook_image -> wf_image -> oi_gal -> gal。"""
    out = []
    for prefix in ('kook_image', 'wf_image', 'oi_gal', 'gal'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp):
                break
            out.extend(json.load(open(fp, encoding='utf-8')))
            i += 1
    return out


def shard_files():
    files = []
    for prefix in ('kook_image', 'wf_image', 'oi_gal', 'gal'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp):
                break
            files.append(fp)
            i += 1
    return files


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

    # ---------- 备份 ----------
    if APPLY:
        bak = os.path.join(ROOT, '_backup_pre_reorg_v6')
        os.makedirs(bak, exist_ok=True)
        for f in files + glob.glob(os.path.join(DATA, 'cp_*.json')) + [os.path.join(DATA, 'manifest.json')]:
            shutil.copy2(f, os.path.join(bak, os.path.basename(f)))
        print('已备份 ->', bak)

    # ---------- A+B：改分片里的分类 ----------
    moved = Counter()
    gpt_n = 0
    for fp in files:
        d = json.load(open(fp, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) < 6:
                continue
            cat = _s(r[3])
            # 任何 GPT 系模型键都并进来（以后源站新增 "GPT Image 3" 之类也不会再拆开）
            if cat != GPT_CAT and (cat in GPT_KEYS or 'gpt' in cat.lower()):
                r[3] = GPT_CAT
                gpt_n += 1
                dirty = True
                continue
            if cat in PORTRAIT_CATS:
                nc, why = strict_classify(r[1], r[2])
                if not nc:
                    nc, why = style_fix(r[1], r[2], cat)
                if nc and nc != cat:
                    moved[(cat, nc, why.split(':')[0])] += 1
                    r[3] = nc
                    dirty = True
        if dirty and APPLY:
            with open(fp, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    print('GPT 系列合并 -> %s : %d 条' % (GPT_CAT, gpt_n))
    print('人像类改判:', sum(moved.values()), '条')
    for (a, b, why), n in moved.most_common():
        print('  %5d  %s -> %s  (%s)' % (n, a, b, why))

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
        if cat in PORTRAIT_CATS:
            ranked = sorted(items, key=score_v6, reverse=True)[:150]
        else:
            ranked = items[:120]
        pack[cat] = name
        total_pack_rows += len(ranked)
        if APPLY:
            with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as fh:
                json.dump(ranked, fh, ensure_ascii=False, separators=(',', ':'))

    # 「全部」首屏包：按分片顺序前 120 条（最新收录优先）
    if APPLY:
        with open(os.path.join(DATA, 'cp_all.json'), 'w', encoding='utf-8') as fh:
            json.dump(rows[:120], fh, ensure_ascii=False, separators=(',', ':'))

    # 「人像（全部）」首屏包：跨全部分类抽人像，按桶轮流取，
    # 首屏写实照片 / 人物 / 二次元 / 其他分类里的人物交替出现，不会一屏全是同一类。
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
        if k in GPT_KEYS or 'gpt' in k.lower():
            del cats_meta[k]
    cats_meta[GPT_CAT] = [GPT_CAT, GPT_ICON]
    man['galCats'] = cats_meta

    cnt = Counter(_s(r[3]) for r in rows if len(r) > 3)
    man.setdefault('catCounts', {})['gal'] = {k: v for k, v in cnt.items()}

    man['galCatPack'] = pack
    man['galAllPack'] = 'cp_all'
    man['portraitAllPack'] = 'cp_portrait_all'
    man['portraitAllCount'] = len(cand)
    man['portraitCats'] = list(PORTRAIT_CATS)
    man['totalCats'] = (len(man.get('cats', {})) + len(man.get('imageCats', {})) +
                        len(man.get('videoCats', {})) + len(man.get('galCats', {})))
    man['uiVersion'] = '2026-11-20-cat-reorg-v6'
    sig = hashlib.md5()
    for k in sorted(pack.keys()):
        sig.update(('%s|%s' % (k, pack[k])).encode('utf-8'))
    sig.update(json.dumps(cand_ranked, ensure_ascii=False).encode('utf-8'))
    sig.update(json.dumps(rows[:120], ensure_ascii=False).encode('utf-8'))
    man['packsSig'] = sig.hexdigest()[:8]
    if APPLY:
        with open(mp, 'w', encoding='utf-8') as fh:
            json.dump(man, fh, ensure_ascii=False, separators=(',', ':'))

    # 清掉已经没有分类引用的旧 cp 包（合并后的 8 个 GPT 小类等）
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
    print('首屏包: %d 个分类 + 全部 + 人像全部 | 行数 %d' % (len(by_cat), total_pack_rows))

    for cat in PORTRAIT_CATS:
        top = sorted(by_cat.get(cat, []), key=score_v6, reverse=True)[:150]
        hd = [_s(r[1])[:70] for r in top]
        anime = sum(1 for h in hd if ART_ANIME.search(h))
        other = sum(1 for h in hd if ART_OTHER.search(h) or SCALE_WEIRD.search(h))
        print('\n=== %s 首屏（%d 条）二次元=%d 艺术合成=%d ===' % (cat, len(top), anime, other))
        for r in top[:8]:
            print('  [%3d] %s' % (score_v6(r), _s(r[1])[:56]))
    print('\n=== 人像（全部）首屏抽样 ===')
    for r in cand_ranked[:10]:
        print('  [%3d] %-10s %s' % (score_all(r), _s(r[3])[:10], _s(r[1])[:48]))

    if not APPLY:
        print('\n[DRY-RUN] 未写盘。加 --apply 生效。')
        return

    # ---------- DATA_VER ----------
    ver = hashlib.md5(open(mp, 'rb').read()).hexdigest()[:8]
    cp = os.path.join(ROOT, 'assets', 'js', 'config.js')
    s = open(cp, encoding='utf-8').read()
    s = re.sub(r"DATA_VER: '[^']*'", "DATA_VER: '%s'" % ver, s)
    open(cp, 'w', encoding='utf-8').write(s)
    print('\nDATA_VER =', ver)


if __name__ == '__main__':
    main()

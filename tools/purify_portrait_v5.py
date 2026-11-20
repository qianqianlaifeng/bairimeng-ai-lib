# -*- coding: utf-8 -*-
"""
人像风格纠错 v5
================
用户反馈：人像写真里还有"超现实主义的巨大美女头部+小人剪发"这类合成艺术作品。

v4 只解决"主语不是人"，没解决"风格不是写实"。v5 增加风格纠错：

  人像写真（只该放写实真人照片）：
    - 标题含 超现实/艺术/动漫/3D/雕塑/拼贴/像素/拟人化/怪物 等 -> 移到「人像动漫」
  人像动漫（只该放动漫/插画/艺术）：
    - 标题是纯写实照片、且无艺术信号 -> 移回「人像写真」

同时保留 v4 的非人像清理与首屏纯度重排。

用法：
  python tools/purify_portrait_v5.py            # DRY-RUN
  python tools/purify_portrait_v5.py --apply    # 写盘
"""
import json, glob, os, sys, re, hashlib, shutil
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
PORTRAIT_CATS = {'人像人物', '人像写真', '人像动漫'}
APPLY = '--apply' in sys.argv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 复用 v4 的非人像清理与评分（避免重复实现、保持规则一致）
from purify_portrait_v4 import (
    strict_classify, portrait_score, has_person_subject, _s,
    DESIGN_SUBJ, BODY_SUBJ, ACCESSORY_SUBJ, NONPERSON_SUBJ, NONPERSON_PROTECT,
    FACE_RELATED, creature_disguised,
)

# ============================================================
# 风格信号
# ============================================================
# 强艺术/非照片（明确不是写实摄影）
STRONG_ART = re.compile(
    r'超现实主义|超现实(?!写实)|surreal|故障艺术|glitch|双重曝光|double exposure|'
    r'数字绘画|digital painting|数字艺术|digital art|3d渲染|3d render|\bc4d\b|'
    r'blender|octane|虚幻引擎|unreal engine|半机械人|cyborg|拟人化|anthropomorph|'
    r'怪物|怪兽|地精|恶魔|monster|goblin|雕塑|雕像|粘土|黏土|毛毡|剪纸|拼贴|collage|'
    r'油画|水彩|插画|illustration|动漫|卡通|cartoon|anime|漫画|manga|木雕|'
    r'像素|pixel art|低多边形|low poly|厚涂|板绘|赛璐璐|cel.?shad|'
    r'布偶|玩偶|手办|盲盒|黏土动画|3d模型|三维模型',
    re.I
)
# 尺度异常/合成感（巨大人头+小人这类超现实构图）
SCALE_WEIRD = re.compile(r'巨大的.{0,6}头部|巨大的.{0,4}脸|微缩.{0,6}人物|巨人|极小的人|'
                         r'站在.{0,6}脚手架上|在.{0,6}头发上|漂浮在空|悬浮在空', re.I)
# 纯写实信号（用于把动漫类里的写实图纠回来）
PURE_REAL = re.compile(
    r'照片|摄影|写真|photograph|photo|realistic|写实|实拍|单反|相机拍摄|镜头|'
    r'肖像照|自拍|selfie|85mm|50mm|f/1\.4|景深', re.I
)


def style_fix(title, prompt, cur_cat):
    """返回 (新分类, 原因) 或 (None,'')"""
    t = _s(title)
    head = t[:70]
    # 超写实（hyperrealistic）是写实，不算超现实 —— 但若同时出现"超现实"，按超现实处理
    is_hyperreal_only = bool(re.search(r'超写实|hyperrealistic', head, re.I)) and not re.search(r'超现实(?!写实)|surreal', head, re.I)

    art = bool(STRONG_ART.search(head)) or bool(SCALE_WEIRD.search(head))

    if cur_cat == '人像写真':
        if art and not is_hyperreal_only:
            m = STRONG_ART.search(head) or SCALE_WEIRD.search(head)
            return '人像动漫', '风格不符(非写实):' + (m.group(0)[:12] if m else '艺术')
    elif cur_cat == '人像动漫':
        # 反向：纯写实照片、无任何艺术信号 -> 纠回人像写真
        if (not art) and PURE_REAL.search(head) and has_person_subject(head):
            return '人像写真', '纯写实照片'
    return None, ''


# ============================================================
def slug(cat):
    return 'cp_' + hashlib.md5(cat.encode('utf-8')).hexdigest()[:10]


def load_shards():
    out = []
    for prefix in ('wf_image', 'oi_gal', 'gal', 'kook_image'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp):
                break
            out.extend(json.load(open(fp, encoding='utf-8')))
            i += 1
    return out


def main():
    if APPLY:
        bak = os.path.join(ROOT, '_backup_pre_portrait_v5')
        os.makedirs(bak, exist_ok=True)
        for f in glob.glob(os.path.join(DATA, 'gal_*.json')) + \
                 glob.glob(os.path.join(DATA, 'cp_*.json')) + \
                 [os.path.join(DATA, 'manifest.json')]:
            shutil.copy2(f, os.path.join(bak, os.path.basename(f)))
        print('已备份 ->', bak)

    changed = {}
    total = 0
    # ---- 1) 风格纠错 + v4 非人清理 ----
    for f in sorted(glob.glob(os.path.join(DATA, 'gal_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) >= 6 and r[3] in PORTRAIT_CATS:
                total += 1
                cur = r[3]
                # 先 v4 非人清理
                nc, why = strict_classify(r[1], r[2])
                if not nc:
                    # 再做风格纠错
                    nc, why = style_fix(r[1], r[2], cur)
                if nc and nc != cur:
                    changed[r[0]] = (cur, nc, why)
                    r[3] = nc
                    dirty = True
        if dirty and APPLY:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    print('人像类条目总数:', total)
    print('本次改动:', len(changed), '条')
    flow = Counter((v[0], v[1]) for v in changed.values())
    print('--- 流向 ---')
    for (a, b), n in flow.most_common():
        print('  %5d  %s -> %s' % (n, a, b))
    reasons = Counter(v[2].split(':')[0] for v in changed.values())
    print('--- 原因 ---')
    for k, n in reasons.most_common():
        print('  %5d  %s' % (n, k))

    # 抽样
    print('\n=== 抽样：人像写真 -> 人像动漫 ===')
    shown = 0
    for rid, (a, b, why) in changed.items():
        if a == '人像写真' and b == '人像动漫' and shown < 18:
            shown += 1
            # 找标题
            print('  ', why)

    # ---- 2) 同步 cp 包 ----
    if APPLY:
        for f in glob.glob(os.path.join(DATA, 'cp_*.json')):
            if os.path.basename(f) == 'cp_all.json':
                continue
            d = json.load(open(f, encoding='utf-8'))
            dirty = False
            for r in d:
                if len(r) >= 6 and r[0] in changed:
                    r[3] = changed[r[0]][1]
                    dirty = True
            if dirty:
                with open(f, 'w', encoding='utf-8') as fh:
                    json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    # ---- 3) 首屏纯度重排 ----
    rows = load_shards()
    by_cat = {}
    for r in rows:
        if len(r) > 3:
            by_cat.setdefault(r[3], []).append(r)

    for cat in ['人像写真', '人像人物', '人像动漫']:
        items = by_cat.get(cat, [])
        top = sorted(items, key=portrait_score, reverse=True)[:120]
        # 检查首屏里还有多少艺术信号
        art_in = sum(1 for r in top if STRONG_ART.search(_s(r[1])[:70]) or SCALE_WEIRD.search(_s(r[1])[:70]))
        print('\n=== %s（共%d，取%d，首屏艺术信号残留=%d）===' % (cat, len(items), len(top), art_in))
        for r in top[:10]:
            print('  [%2d] %s' % (portrait_score(r), _s(r[1])[:60]))

    if not APPLY:
        print('\n[DRY-RUN] 未写盘。')
        return

    # ---- 4) 写回 cp 包 ----
    for cat, items in by_cat.items():
        name = slug(cat)
        ranked = sorted(items, key=portrait_score, reverse=True)[:120]
        with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(ranked, fh, ensure_ascii=False, separators=(',', ':'))
    print('\n重建 cp 包:', len(by_cat), '类')

    # ---- 5) manifest 计数 ----
    mp = os.path.join(DATA, 'manifest.json')
    man = json.load(open(mp, encoding='utf-8'))
    cnt = Counter(r[3] for r in rows if len(r) > 3 and not str(r[3]).startswith(('oi-', 'wf-', 'kook-')))
    for k, v in cnt.items():
        man['catCounts']['gal'][k] = v
    man['uiVersion'] = '2026-11-20-portrait-purify-v5'
    with open(mp, 'w', encoding='utf-8') as fh:
        json.dump(man, fh, ensure_ascii=False, separators=(',', ':'))
    print('人像计数: 写真=%d 人物=%d 动漫=%d' % (
        cnt.get('人像写真', 0), cnt.get('人像人物', 0), cnt.get('人像动漫', 0)))

    # ---- 6) DATA_VER ----
    ver = hashlib.md5(open(mp, 'rb').read()).hexdigest()[:8]
    cp = os.path.join(ROOT, 'assets', 'js', 'config.js')
    s = open(cp, encoding='utf-8').read()
    s2 = re.sub(r"DATA_VER: '[^']*'", "DATA_VER: '%s'" % ver, s)
    open(cp, 'w', encoding='utf-8').write(s2)
    h = hashlib.md5(open(cp, 'rb').read()).hexdigest()[:8]
    ip = os.path.join(ROOT, 'index.html')
    t = open(ip, encoding='utf-8').read()
    t2 = re.sub(r'assets/js/config\.js(\?v=[0-9a-f]+)?', 'assets/js/config.js?v=' + h, t)
    open(ip, 'w', encoding='utf-8').write(t2)
    print('DATA_VER =', ver, '| config.js?v=', h)


if __name__ == '__main__':
    main()

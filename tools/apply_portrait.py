# -*- coding: utf-8 -*-
"""
执行人像分类重组 (复用 classify_portrait.py 的分类规则):
  1) 遍历 gal_*.json 改分类字段 (人像写真/人像人物/人像动漫 + 少量非人物归位)
  2) 重建所有 cp 首屏包 (build_catpack 约定: cp_ = md5(cat)[:10])
  3) 更新 manifest: 新增"人像动漫"分类、三人像类相邻、重算 catCounts.gal
  4) 更新 config.js 的 DATA_VER (md5(manifest)[:8]) 与 index.html 的 ?v=

支持 --dry 只预演不写盘。
"""
import json, glob, os, sys, hashlib, re, shutil
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify_portrait import classify, PORTRAIT_CATS, DATA, ROOT

DRY = '--dry' in sys.argv
NEW_CAT = '人像动漫'
EMOJI = '🧊'

def slug(cat):
    return 'cp_' + hashlib.md5(cat.encode('utf-8')).hexdigest()[:10]

def load_shards():
    out = []
    for prefix in ('wf_image', 'oi_gal', 'gal', 'kook_image'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp): break
            out.extend(json.load(open(fp, encoding='utf-8')))
            i += 1
    return out

def main():
    # 备份关键文件
    if not DRY:
        bak = os.path.join(ROOT, '_backup_pre_portrait')
        os.makedirs(bak, exist_ok=True)
        for f in glob.glob(os.path.join(DATA, 'gal_*.json')) + [os.path.join(DATA, 'manifest.json')]:
            shutil.copy2(f, os.path.join(bak, os.path.basename(f)))
        print('已备份 ->', bak)

    changed = {}
    # 1) 改 gal 分片
    for f in sorted(glob.glob(os.path.join(DATA, 'gal_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) >= 6 and r[3] in PORTRAIT_CATS:
                nc, why = classify(r[1], r[2])
                if nc and nc != r[3]:
                    changed[r[0]] = (r[3], nc)
                    r[3] = nc
                    dirty = True
        if dirty and not DRY:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
    print('改分类条目:', len(changed))
    flow = Counter(changed.values())
    for (a, b), n in flow.most_common(): print(f'  {n:5d}  {a} -> {b}')

    # 2) 重建 cp 包 (需基于改后的全量分片)
    #    DRY 模式下跳过重建以免污染; apply 下用 build_catpack 逻辑内联
    if not DRY:
        rows = load_shards()
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r[3] if len(r) > 3 else '', []).append(r)
        for cat, items in by_cat.items():
            name = slug(cat)
            with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as fh:
                json.dump(items[:120], fh, ensure_ascii=False, separators=(',', ':'))
        print('重建 cp 包:', len(by_cat), '类; 人像动漫条目=', len(by_cat.get(NEW_CAT, [])))

    # 3) 更新 manifest
    mp = os.path.join(DATA, 'manifest.json')
    man = json.load(open(mp, encoding='utf-8'))
    # galCats 顺序: 把三个人像类相邻放在最前
    galcats = man['galCats']
    portrait_keys = ['人像写真', '人像人物', NEW_CAT]
    # 新增 人像动漫
    if NEW_CAT not in galcats:
        galcats[NEW_CAT] = [NEW_CAT, EMOJI]
    others = [(k, v) for k, v in galcats.items() if k not in portrait_keys]
    new_order = {}
    for k in portrait_keys:
        new_order[k] = [k, EMOJI] if k == NEW_CAT else galcats[k]
    for k, v in others:
        new_order[k] = v
    man['galCats'] = new_order
    # galCatPack: 记录新类文件名
    man.setdefault('galCatPack', {})[NEW_CAT] = slug(NEW_CAT)
    # 重算 catCounts.gal (基于改后分片)
    rows = load_shards()
    cnt = Counter(r[3] for r in rows if len(r) > 3 and not str(r[3]).startswith(('oi-', 'wf-', 'kook-')))
    for k, v in cnt.items():
        man['catCounts']['gal'][k] = v
    man['uiVersion'] = '2026-11-20-portrait-clean'
    if not DRY:
        with open(mp, 'w', encoding='utf-8') as fh:
            json.dump(man, fh, ensure_ascii=False, separators=(',', ':'))
    print('人像计数: 写真=%d 人物=%d 动漫=%d' % (
        man['catCounts']['gal'].get('人像写真', 0),
        man['catCounts']['gal'].get('人像人物', 0),
        man['catCounts']['gal'].get(NEW_CAT, 0)))
    print('galCats 前排顺序:', list(man['galCats'].keys())[:6])

    # 4) DATA_VER
    if not DRY:
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 KOOK 三个分类的 gal 行补第 8 字段: 发布时间(YYYY-MM-DD)。

用途: 前端「最新在前」排序需要真实时间。kook_image_*.json 是一次性快照,
每日 Actions 不会重写它们, 所以补一次即可长期有效; 万一重建了快照, 带上
--src 指向 kookaigc 列表缓存(_kook_all.json) 重跑本脚本即可。

用法:
  python tools/enrich_kook_time.py --src D:/AI/2026-10-10-14-08-45/.cache/_kook_all.json
  python tools/enrich_kook_time.py            # 自动生成 data/kook_times.json 时用默认源
"""
import argparse
import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
DEFAULT_SRC = r'D:/AI/2026-10-10-14-08-45/.cache/_kook_all.json'
TIMES_FILE = os.path.join(DATA, 'kook_times.json')


def load_times(src):
    if os.path.exists(src):
        rows = json.load(open(src, encoding='utf-8'))
        out = {}
        for im in rows:
            t = (im.get('upload_time') or '')[:10]
            if t:
                out['kook-' + str(im.get('id'))] = t
        print('[time] 从缓存读取', len(out), '条时间:', src)
        return out
    if os.path.exists(TIMES_FILE):
        out = json.load(open(TIMES_FILE, encoding='utf-8'))
        print('[time] 从 data/kook_times.json 读取', len(out), '条时间')
        return out
    raise SystemExit('[time] 找不到时间来源，请用 --src 指定 _kook_all.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=DEFAULT_SRC)
    args = ap.parse_args()
    times = load_times(args.src)
    if not os.path.exists(TIMES_FILE):
        json.dump(times, open(TIMES_FILE, 'w', encoding='utf-8'), ensure_ascii=False)

    files = sorted(glob.glob(os.path.join(DATA, 'kook_image_*.json')))
    for cat in ('kook-rumengsihuan', 'kook-gpt-image', 'kook-yaoguang'):
        import hashlib
        files.append(os.path.join(DATA, 'cp_' + hashlib.md5(cat.encode()).hexdigest()[:10] + '.json'))

    total = hit = 0
    for fp in files:
        if not os.path.exists(fp):
            print('[time] 跳过(不存在)', os.path.basename(fp))
            continue
        rows = json.load(open(fp, encoding='utf-8'))
        changed = 0
        for r in rows:
            if not (isinstance(r, list) and str(r[0]).startswith('kook-')):
                continue
            total += 1
            t = times.get(str(r[0]), '')
            if not t:
                continue
            hit += 1
            if len(r) < 8:
                r.append(t)
            else:
                r[7] = t
            changed += 1
        if changed:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(json.dumps(rows, ensure_ascii=False))
            print('[time]', os.path.basename(fp), '更新', changed, '行')
    print('[time] 完成: kook 行', total, '| 匹配到时间', hit)


if __name__ == '__main__':
    main()

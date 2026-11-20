# -*- coding: utf-8 -*-
"""把 KOOK（最新收录：瑶光 / 如梦似幻）的封面换成高分辨率原图。

背景：站点里 media/kook/*.webp 原来存的是接口给的 480px 缩略图，
卡片上够用，但点开大图放大会糊。KOOK 图床的原图是 1920 长边、而且体积
只有 60KB 左右（本来就是 webp），所以直接换成原图最划算。

图床对空 Referer 会 403，必须带 Referer: https://kookaigc.top/ 。

用法：
    python tools/upgrade_kook_images.py           # 干跑，只看会换多少张
    python tools/upgrade_kook_images.py --apply   # 真下载并覆盖
    python tools/upgrade_kook_images.py --apply --limit 20   # 只处理前 20 张
"""
import glob
import io
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
MEDIA = os.path.join(ROOT, 'media', 'kook')
APPLY = '--apply' in sys.argv
LIMIT = 0
if '--limit' in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index('--limit') + 1])

CDN = 'https://img.kookaigc.top/cos-image/%s.webp'
CDN_SIZED = 'https://img.kookaigc.top/cos-image/%s.webp?imageMogr2/thumbnail/1280x%%3E/format/webp/quality/82'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'),
    'Referer': 'https://kookaigc.top/',
    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
}
MAX_W = 1280          # 存盘最长边：弹窗最大显示 ~900px，1280 足够清晰且不臃肿
QUALITY = 82


MAP = {}


def load_map():
    """可选: --map kook_urls.json (id -> https://img.kookaigc.top/cos-image/xxx.webp?...) 
    接口返回的文件名有时跟图片 id 不一样, 有这张表就不用猜。"""
    if '--map' not in sys.argv:
        return
    fp = sys.argv[sys.argv.index('--map') + 1]
    for x in json.load(open(fp, encoding='utf-8')):
        if x.get('id') and x.get('url'):
            MAP[x['id']] = x['url'].split('?')[0]


def kook_ids():
    """从数据里收集所有 media/kook/<id>.webp 的 id（去重、保持顺序）"""
    ids = []
    seen = set()
    for f in sorted(glob.glob(os.path.join(DATA, '*.json'))):
        name = os.path.basename(f)
        if name == 'manifest.json':
            continue
        try:
            rows = json.load(open(f, encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, list) or len(r) < 6:
                continue
            m = re.match(r'^media/kook/([0-9a-zA-Z_-]+)\.webp$', str(r[5] or ''))
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                ids.append(m.group(1))
    return ids


def local_size(iid):
    p = os.path.join(MEDIA, iid + '.webp')
    if not os.path.exists(p):
        return 0, 0
    try:
        with Image.open(p) as im:
            return im.size
    except Exception:
        return 0, 0


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def upgrade(iid):
    w0, h0 = local_size(iid)
    if w0 >= MAX_W * 0.95:
        return ('skip', iid, (w0, h0), 0)
    body = None
    cands = []
    if MAP.get(iid):
        cands.append(MAP[iid])
    cands += [CDN % iid, CDN_SIZED % iid]
    for url in cands:
        try:
            body = fetch(url)
            break
        except Exception:
            body = None
    if not body:
        return ('fail', iid, (w0, h0), 0)
    try:
        im = Image.open(io.BytesIO(body))
        im.load()
    except Exception:
        return ('fail', iid, (w0, h0), 0)
    w, h = im.size
    if w < max(w0 * 1.3, 700):        # 拿到的还没本地大，不换
        return ('small', iid, (w0, h0), len(body))
    if w > MAX_W:
        im = im.convert('RGB') if im.mode in ('RGBA', 'P') else im
        im.thumbnail((MAX_W, MAX_W * 4), Image.LANCZOS)
    if not APPLY:
        return ('would', iid, (w0, h0), len(body))
    os.makedirs(MEDIA, exist_ok=True)
    out = os.path.join(MEDIA, iid + '.webp')
    tmp = out + '.tmp'
    im.save(tmp, 'WEBP', quality=QUALITY, method=6)
    os.replace(tmp, out)
    return ('ok', iid, (w0, h0), os.path.getsize(out))


def main():
    load_map()
    ids = kook_ids()
    if LIMIT:
        ids = ids[:LIMIT]
    print('数据里引用到的 KOOK 图: %d 张 (本地目录 %d 个文件)' %
          (len(ids), len(glob.glob(os.path.join(MEDIA, '*.webp')))))
    todo = [i for i in ids if local_size(i)[0] < MAX_W * 0.95]
    print('需要升级(宽度<1200):', len(todo))
    if not todo:
        print('已经是高清版，不用动。')
        return

    stat = {'ok': 0, 'would': 0, 'skip': 0, 'small': 0, 'fail': 0}
    fails = []
    saved = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, (kind, iid, old, nbytes) in enumerate(ex.map(upgrade, todo), 1):
            stat[kind] = stat.get(kind, 0) + 1
            if kind == 'ok':
                saved += nbytes
            if kind == 'fail':
                fails.append(iid)
            if i % 50 == 0 or i == len(todo):
                print('  %d/%d  ok=%d fail=%d' % (i, len(todo), stat['ok'], stat['fail']))
    print('结果:', stat)
    if APPLY and saved:
        print('高清图总计 %.1f MB' % (saved / 1048576))
    if fails:
        print('失败(CDN 上没有/超时):', len(fails), fails[:8])
    if not APPLY:
        print('\n[DRY-RUN] 未写盘。加 --apply 生效。')


if __name__ == '__main__':
    main()

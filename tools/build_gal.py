#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把抓取结果转成站点分片。
记录格式: [id, title, body, cat, desc, cover, refs?]
  - id    : g-<hash>             (中性, 不含来源痕迹)
  - title : 从提示词派生的短标题(去参数)
  - body  : 提示词全文(已剥掉所有链接)
  - cat   : 中文分类 key
  - desc  : ""
  - cover : /m/<代号>/<路径>      (走图片代理, 浏览器看不到图床域名)
  - refs  : [["sref","/m/i/x.png"], ...]  风格/角色参考图(有才带这一位)

来源相关的域名/密钥统一从 sitecfg 读取, 本文件不含任何来源信息。
"""
import json, os, re, sys, hashlib, collections, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sitecfg import HOST_TOKEN, BANNED, LEAK_RE  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# 输出目录可用 GAL_OUTDIR 覆盖(仓库里的 tools/ 版本会指向 ../data)
RAW = os.environ.get("GAL_RAW") or os.path.join(HERE, ".cache", "discovery.json")
OUTDIR = os.environ.get("GAL_OUTDIR") or os.path.join(HERE, "app", "data")
PER = 600

CAT_MAP = {
    "IllustrationAndComic": ("插画漫画", "🖌️"),
    "ThemeBattle": ("主题挑战", "⚔️"),
    "Portraits": ("人像写真", "👤"),
    "Default": ("综合精选", "✨"),
    "InteriorArchitecture": ("室内建筑", "🏛️"),
    "DailyLife": ("日常生活", "🌿"),
    "GameOriginalPainting": ("游戏原画", "🎮"),
    "FlatLogoUI": ("平面界面", "💻"),
    "ProductDesign": ("产品设计", "🛍️"),
    "EcommerceDisplay": ("电商展示", "🏷️"),
    "HotVideo": ("热门视频", "🎬"),
}
KEY_RULES = [
    ("人像人物", "👤", ["人像", "少女", "女孩", "女生", "男孩", "男人", "女人", "人物", "肖像", "模特",
                    "portrait", "girl", "boy", "woman", "man ", "face", "自拍", "cos"]),
    ("风景自然", "🏞️", ["风景", "山", "海", "森林", "天空", "云", "湖", "雪", "日落", "夕阳", "花", "树",
                    "landscape", "mountain", "forest", "sunset", "ocean", "beach", "sky", "nature"]),
    ("建筑空间", "🏛️", ["建筑", "室内", "房间", "城市", "街", "庭院", "客厅", "卧室", "咖啡馆",
                    "interior", "architecture", "city", "room", "street", "building"]),
    ("产品电商", "🛍️", ["产品", "商品", "包装", "广告", "海报", "电商", "品牌", "主图",
                    "product", "poster", "packaging", "advert", "ecommerce", "brand"]),
    ("插画动漫", "🖌️", ["插画", "动漫", "二次元", "漫画", "国漫", "卡通", "绘本",
                    "anime", "comic", "illustration", "cartoon", "manga"]),
    ("游戏原画", "🎮", ["游戏", "角色", "原画", "战士", "法师", "骑士", "boss", "皮肤",
                    "game", "character", "warrior", "mage", "knight"]),
    ("平面界面", "💻", ["logo", "图标", "界面", "平面", "排版", "字体", "icon", "ui ", "banner"]),
    ("动物自然", "🐾", ["猫", "狗", "动物", "兽", "鸟", "龙", "宠物", "animal", "cat", "dog", "dragon", "bird"]),
]
FALLBACK = ("综合精选", "✨")

# ---- 来源清洗 ----
# 一律剥掉提示词里出现的任何 http(s) 链接(源站/参考图/风格引用), 避免暴露数据来源
LEAK_URL = re.compile(r'https?://\S+', re.I)
# URL 被移除后残留的空参考参数(--sref/--cref/--dref/--oref 后面没有值了)
REF_FLAG = re.compile(r'--(?:sref|cref|dref|oref)\b(?=\s*--|\s*$)', re.I)


def clean_prompt(s):
    s = LEAK_URL.sub(' ', s or '')
    s = REF_FLAG.sub(' ', s)
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = re.sub(r'\s+([，。；：、])', r'\1', s)
    return s.strip()


def has_leak(s):
    if any(b in (s or '') for b in BANNED):
        return True
    return bool(LEAK_RE.search(s or ''))


def classify(cat_en, prompt):
    if cat_en and cat_en in CAT_MAP:
        return CAT_MAP[cat_en]
    low = (prompt or "").lower()
    for label, icon, kws in KEY_RULES:
        for kw in kws:
            if kw in low:
                return (label, icon)
    return FALLBACK


def make_title(prompt):
    t = re.split(r"\s--\w", prompt or "")[0]
    t = re.sub(r"\s+", " ", t).strip() or (prompt or "").strip()
    return t[:34] + ("…" if len(t) > 34 else "")


# 主机名 -> 单字母代号(见 sitecfg)。主机名只出现在服务端(server.js / Cloudflare
# Worker), 站点数据里只有代号 + 路径, 所以静态托管也看不到图床域名。
def cover_path(raw):
    """从原始 imgUrls 里取出 (代号, 路径)。取不到返回 ("", "")。"""
    u = raw
    if isinstance(u, str):
        try:
            u = json.loads(u)
        except Exception:
            pass
    url = u.get("url") if isinstance(u, dict) else u
    if not url:
        return "", ""
    m = re.match(r"^https?://([^/]+)/(.+)$", url.split("?")[0])
    if not m:
        return "", ""
    t = HOST_TOKEN.get(m.group(1).lower())
    return (t, m.group(2)) if t else ("", "")


def url_path(url):
    """任意绝对地址 -> (代号, 路径)。取不到返回 ("", "")。"""
    if not url or not isinstance(url, str):
        return "", ""
    m = re.match(r"^https?://([^/]+)/(.+)$", url.split("?")[0])
    if not m:
        return "", ""
    t = HOST_TOKEN.get(m.group(1).lower())
    return (t, m.group(2)) if t else ("", "")


def url_path(url):
    """任意绝对地址 -> (代号, 路径)。取不到返回 ("", "")。"""
    if not url or not isinstance(url, str):
        return "", ""
    m = re.match(r"^https?://([^/]+)/(.+)$", url.split("?")[0])
    if not m:
        return "", ""
    t = HOST_TOKEN.get(m.group(1).lower())
    return (t, m.group(2)) if t else ("", "")


# 风格/角色参考图: --sref/--cref/--dref/--oref <url>, 以及提示词开头直接给的输入图
REF_FLAG_RE = re.compile(r"--(sref|cref|dref|oref)\s+(https?://\S+)", re.I)
LEAD_URL_RE = re.compile(r"^(https?://\S+)")


def refs_of(full_command):
    """从原始提示词里取出风格参考图, 转成 /m/<代号>/<路径>。

    只保留能走本站代理的主机; 外部第三方图床(midjourney 等)直接丢弃,
    避免把来源暴露出去, 也避免代理变成任人使用的开放转发。
    """
    out, seen = [], set()
    for m in REF_FLAG_RE.finditer(full_command or ""):
        tok, path = url_path(m.group(2))
        if tok:
            u = "/m/%s/%s" % (tok, path)
            if u not in seen:
                seen.add(u)
                out.append([m.group(1).lower(), u])
    m = LEAD_URL_RE.match((full_command or "").strip())
    if m:
        tok, path = url_path(m.group(1))
        if tok:
            u = "/m/%s/%s" % (tok, path)
            if u not in seen:
                seen.add(u)
                out.append(["ref", u])
    return out


def main():
    items = json.load(open(RAW, encoding="utf-8"))
    recs, catcnt, seen = [], collections.Counter(), set()
    dropped, noimg = 0, 0
    skipped_stub = 0
    nref = 0
    for it in items:
        oid = it.get("id")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        # 图片流里 category=HotVideo 的条目只是视频缩略图占位;
        # 真视频由 build_hotvideo.py 单独做进「视频提示词」标签, 画廊保持纯图片
        if it.get("category") == "HotVideo":
            skipped_stub += 1
            continue
        raw = it.get("fullCommand") or ""
        prompt = clean_prompt(raw)
        if not prompt or has_leak(prompt):
            dropped += 1
            continue
        label, _ = classify(it.get("category"), prompt)
        catcnt[label] += 1
        tok, path = cover_path(it.get("imgUrls"))
        if not tok:
            noimg += 1
        rec = ["g-" + hashlib.md5(oid.encode()).hexdigest()[:12],
               make_title(prompt), prompt, label, "",
               ("/m/%s/%s" % (tok, path)) if tok else ""]
        refs = refs_of(raw)
        if refs:
            rec.append(refs)
            nref += 1
        recs.append(rec)
    if skipped_stub:
        print("跳过图片流里的视频缩略图占位: %d 条" % skipped_stub)
    if nref:
        print("带风格参考图: %d 条" % nref)
    n = math.ceil(len(recs) / PER)
    for i in range(n):
        json.dump(recs[i * PER:(i + 1) * PER],
                  open(os.path.join(OUTDIR, "gal_%d.json" % i), "w", encoding="utf-8"),
                  ensure_ascii=False)
    print("总条数:", len(recs), "| 分片:", n, "| 无图:", noimg, "| 因来源清洗剔除:", dropped)
    print("分类统计:", dict(catcnt.most_common()))
    # 分类元信息(供 manifest)
    allcats = {}
    for _, v in CAT_MAP.items():
        allcats[v[0]] = [v[0], v[1]]
    for label, icon, _ in KEY_RULES:
        allcats[label] = [label, icon]
    allcats[FALLBACK[0]] = [FALLBACK[0], FALLBACK[1]]
    meta = {"cats": {k: allcats[k] for k in allcats if catcnt.get(k)},
            "counts": dict(catcnt), "chunks": n, "total": len(recs)}
    json.dump(meta, open(os.path.join(os.path.dirname(RAW), "gal_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("分类元信息 -> %s" % os.path.join(os.path.dirname(RAW), "gal_meta.json"))


if __name__ == "__main__":
    main()

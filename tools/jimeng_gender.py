# -*- coding: utf-8 -*-
"""即梦作品的「人像 / 性别」判定（数据层，随每日刷新实时重算）。

三层判定，优先级从高到低：
  1) 人工逐张看图固化的标签  tools/jimeng_portrait_labels.json
     —— 按作品 ID 存，刷新不会冲掉（即梦数据每天重抓，ID 稳定）。
  2) 文案自动判定（标题 + 提示词）。新作品第一次进来时靠它兜底，
     保证「即梦·人像」在抓取当天就有内容，不会等人工。
  3) 都认不出 -> 不算人像，也不给性别（保留在即梦原分类里）。

判定口径：
  portrait : 画面主体是不是人（含真人照片、动漫立绘、角色设定、半身/全身/头像）
  gender   : 'F' 女 / 'M' 男 / '' 认不出（多人、背影、剪影、中性一律留空）
             留空的仍算人像，只是不进 ♀/♂ 视图 —— 宁可少分，不要分错。

自动判定的取舍：不用泛词（"美""帅""人物"太泛会误伤），只用明确性别词；
标题主语区优先，正文兜底（提示词里常把主体写在开头）。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "jimeng_portrait_labels.json")

# ---------- 谁算「人」 ----------
# 非人主体：命中就基本不是人像（商品/建筑/风景/动物/纯版式）
NOT_PERSON = re.compile(
    r"产品摄影|产品图|商品图|静物|白底图|详情页|电商主图|卖点图|包装设计|礼盒|"
    r"logo|标志设计|字体设计|书法|海报设计|版式|排版|画册|折页|易拉宝|信息图|"
    r"建筑|室内|空间渲染|景观|风景|山川|海景|城市|街道|公路|"
    r"动物|猫|狗|鸟|龙|神兽|机甲|机器人|汽车|摩托车|飞机|飞船|"
    r"三视图|设定稿|配色板|图标|icon|表情包|壁纸|纹理|材质",
    re.I)

# 人像的强信号
PERSON_STRONG = re.compile(
    r"人像|肖像|写真|自拍|证件照|大头照|头像照|半身照|全身照|立绘|角色设定|"
    r"模特|cosplay|coser|人物特写|面部特写|面部细节|三点布光|棚拍人像|"
    r"portrait|selfie|headshot|half[- ]body|full[- ]body|character sheet",
    re.I)

# 人物身份词（标题里出现基本就是有人）
PERSON_WORD = re.compile(
    r"女人|男人|女孩|男孩|女性|男性|少女|少年|女子|男子|女士|先生|美女|美人|帅哥|"
    r"姑娘|小伙|新娘|新郎|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|"
    r"人物|人像|肖像|模特|老人|小孩|儿童|婴儿|少女感|小姐姐|"
    r"woman|women|man\b|men\b|girl|boy|female|male|model|lady|gentleman|person|people|human",
    re.I)

# ---------- 性别词 ----------
FEM = ["女性", "女人", "女孩", "女生", "女子", "女士", "少女", "美女", "美人", "女神",
       "姑娘", "新娘", "妈妈", "母亲", "姐姐", "妹妹", "阿姨", "奶奶", "外婆", "女儿",
       "妻子", "老婆", "大小姐", "御姐", "空姐", "护士", "少女感", "她", "姐妹"]
MAS = ["男性", "男人", "男孩", "男生", "男子", "男士", "少年", "帅哥", "美男", "小伙",
       "大叔", "老头", "大爷", "爷爷", "爸爸", "父亲", "哥哥", "弟弟", "叔叔", "儿子",
       "新郎", "老先生", "他", "兄弟", "小伙儿"]
FEM_EN = ["woman", "women", "girl", "female", "lady", "she", "her", "bride", "actress",
          "princess", "queen", "mom", "mother", "sister", "daughter"]
MAS_EN = ["man", "men", "boy", "male", "gentleman", "he", "his", "groom", "actor",
          "prince", "king", "dad", "father", "brother", "son"]

# 多人/中性：出现这些就不判男女（避免"一对情侣"被硬判成女）
MULTI = re.compile(r"多人|人群|情侣|夫妻|双人|两人|三人|一群|众人|路人|剪影|背影|"
                   r"group|couple|two people|back view|silhouette", re.I)


def _has(text, words, en_words):
    """中文直接包含；英文按词边界（避免 he 命中 the、she 命中 sheer）。"""
    for w in words:
        if w in text:
            return True
    for w in en_words:
        if re.search(r"\b" + w + r"\b", text, re.I):
            return True
    return False


def detect_gender(text):
    """返回 'F' / 'M' / ''。主语区（前 40 字）优先，其次全文。"""
    t = str(text or "")
    if not t:
        return ""
    head = t[:40]
    for seg in (head, t):
        f = _has(seg, FEM, FEM_EN)
        m = _has(seg, MAS, MAS_EN)
        if f and not m:
            return "F"
        if m and not f:
            return "M"
        if f and m:
            # 两者都有：取更早出现的那个（"一位男性画师笔下的女孩" 取男）
            pf = min([seg.find(w) for w in FEM if w in seg] or [10 ** 9])
            pm = min([seg.find(w) for w in MAS if w in seg] or [10 ** 9])
            for w in FEM_EN:
                mm = re.search(r"\b" + w + r"\b", seg, re.I)
                if mm:
                    pf = min(pf, mm.start())
            for w in MAS_EN:
                mm = re.search(r"\b" + w + r"\b", seg, re.I)
                if mm:
                    pm = min(pm, mm.start())
            if pf != pm:
                return "F" if pf < pm else "M"
            return ""      # 同位置分不出，不猜
    return ""


def _strip_negative(body):
    b = str(body or "")
    b = re.split(r"--no\b|negative\s*prompt|负面提示词|负面词|\bno\s+(?:text|logo)", b, flags=re.I)[0]
    return b.strip()


def guess(title, prompt):
    """自动判定 -> (portrait:int, gender:str)。认不出返回 (0, '')。"""
    title = str(title or "")
    body = _strip_negative(prompt)[:300]
    t40 = title[:40]
    text = (title + " " + body)

    # 人像信号：标题里有人物身份词 / 提示词开头有人物身份词 / 明确的写真类术语。
    # 正文只看前 60 字 —— 提示词一般把主体写在开头，后面的场景词容易误伤。
    person = (bool(PERSON_WORD.search(t40)) or bool(PERSON_STRONG.search(text))
              or bool(PERSON_WORD.search(body[:60])))
    # 明确的非人主体 + 没有任何人像信号 -> 不是人像
    if not person:
        return 0, ""
    if NOT_PERSON.search(t40) and not PERSON_STRONG.search(text):
        return 0, ""
    if MULTI.search(text):
        return 1, ""
    g = detect_gender(t40) or detect_gender(body)
    return 1, g


_cache = {"mtime": None, "data": {}}


def load_labels():
    """人工逐张看图的标签（按 ID 固化）。文件变了会自动重读。"""
    try:
        mt = os.path.getmtime(LABELS)
    except OSError:
        return {}
    if _cache["mtime"] == mt:
        return _cache["data"]
    try:
        d = json.load(open(LABELS, encoding="utf-8"))
        _cache["data"] = d if isinstance(d, dict) else {}
        _cache["mtime"] = mt
    except Exception:
        _cache["data"] = {}
    return _cache["data"]


def label_for(rid, title, prompt):
    """先查人工标签，再退回自动判定。"""
    lab = load_labels().get(rid)
    if isinstance(lab, dict):
        return int(lab.get("portrait") or 0), str(lab.get("gender") or "")
    return guess(title, prompt)

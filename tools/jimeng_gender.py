# -*- coding: utf-8 -*-
"""即梦作品的「人像 / 性别」判定（数据层，随每次抓取重算）。

三层判定，优先级从高到低：
  1) 人工逐张看图固化的标签  tools/jimeng_portrait_labels.json
     —— 按作品 ID 存，刷新不会冲掉（即梦数据每天重抓，ID 稳定）。
  2) 视觉模型逐张看封面打出的标签  tools/jimeng_vision_labels.json
     —— 数据量大时的主要来源，由 tools/vision_label_jimeng.py 生成。
  3) 性别识别模型的高置信输出  tools/jimeng_model_gender.json
     —— 只在人脸检测+对齐后性别置信度足够高才给 F/M
        （274 条真值上 |d|>=3.0 档实测准确率 92.7% / 覆盖 50%），
        置信不足的一律留空。由 tools/gender_model_label.py 生成。
  4) 文案兜底（标题 + 提示词）。只用来**收窄**候选池，判定口径刻意保守：
     宁可漏几条，也不要把商品图/海报塞进人像（人像里混错图比少几条更伤）。

判定口径：
  portrait : 画面主体是不是人（真人照片、动漫立绘、角色设定、半身/全身/头像）
  gender   : 'F' 女 / 'M' 男 / '' 认不出（多人、背影、剪影、中性一律留空）
             留空的仍算人像，只是不进 ♀/♂ 视图 —— 宁可少分，不要分错。

文案规则为什么这么保守：
  在这批数据上跑过回归 —— 宽松规则召回高但精确率只有 67%（把"猫/三视图/海报"
  误判成人像）；收紧到"必须有明确人物主体词，且不能是版式/商品/动物/多视角设定稿"
  之后精确率到 90%+，剩下漏掉的交给视觉模型补。
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "jimeng_portrait_labels.json")
VISION = os.path.join(HERE, "jimeng_vision_labels.json")
MODEL = os.path.join(HERE, "jimeng_model_gender.json")

# ---------- 明确不是人像 ----------
# 命中即否决（除非同时出现强人像词，见下）
NOT_PERSON = re.compile(
    r"三视图|设定稿|配色板|色板|多视角|正面\+侧面|正面 \+ 侧面|"
    r"logo|标志设计|字体设计|书法|毛笔字|艺术字|字体海报|"
    r"海报设计|宣传海报|活动海报|版式|排版|画册|折页|易拉宝|信息图|长图|"
    r"产品摄影|产品图|商品图|静物|白底图|详情页|电商主图|卖点图|包装设计|"
    r"手办|盲盒|潮玩|公仔|泡泡玛特|人偶|贴纸|"
    r"建筑|室内设计|空间渲染|景观|风景|山川|海景|城市|街道|"
    r"图标|icon|表情包|壁纸|纹理|材质|"
    r"\bcat\b|\bdog\b|猫咪|猫粮|小猫|狗狗|动物|神兽|龙|机甲|机器人|"
    r"汽车|摩托车|飞机|飞船",
    re.I)

# 强人像信号：出现这些即使是海报/插画也按人像算（如"人像海报""角色立绘"）
PERSON_STRONG = re.compile(
    r"人像摄影|人像特写|人像写真|肖像照|人物写真|人物特写|人物肖像|"
    r"半身像|全身像|头像照|证件照|自拍|"
    r"portrait|selfie|headshot|half[- ]body|full[- ]body",
    re.I)

# 人物主体词（标题里作为"人"的证据）
PERSON_WORD = re.compile(
    r"女人|男人|女孩|男孩|女性|男性|少女|少年|女子|男子|美女|美人|帅哥|"
    r"姑娘|小伙|新娘|新郎|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|"
    r"模特|人物|人像|肖像|老人|小孩|儿童|婴儿|小姐姐|辣妹|御姐|熟女|"
    r"woman|women|man\b|men\b|girl|boy|female|male|model|lady|gentleman|person|people",
    re.I)

# 排版/信息图类强特征（正文里出现就基本不是人像主体）
LAYOUT = re.compile(r"主标题|副标题|标题字|文案|标语|留白|信息层级|排版|网格|底部文字|顶部文字|"
                    r"画面上方|画面下方|左侧文字|右侧文字", re.I)

FEM = ["女性", "女人", "女孩", "女生", "女子", "女士", "少女", "美女", "美人", "女神",
       "姑娘", "新娘", "妈妈", "母亲", "姐姐", "妹妹", "阿姨", "奶奶", "外婆", "女儿",
       "妻子", "老婆", "大小姐", "御姐", "空姐", "护士", "少女感", "她", "姐妹",
       "辣妹", "熟女", "剩女", "美少女"]
MAS = ["男性", "男人", "男孩", "男生", "男子", "男士", "少年", "帅哥", "美男", "小伙",
       "大叔", "老头", "大爷", "爷爷", "爸爸", "父亲", "哥哥", "弟弟", "叔叔", "儿子",
       "新郎", "老先生", "他", "兄弟", "小伙儿"]
FEM_EN = ["woman", "women", "girl", "female", "lady", "she", "her", "bride", "actress",
          "princess", "queen", "mom", "mother", "sister", "daughter"]
MAS_EN = ["man", "men", "boy", "male", "gentleman", "he", "his", "groom", "actor",
          "prince", "king", "dad", "father", "brother", "son"]

MULTI = re.compile(r"多人|人群|情侣|夫妻|双人|两人|三人|一群|众人|路人|剪影|背影|"
                   r"group|couple|two people|back view|silhouette", re.I)


# 画风/文体词：含性别字但描述的是画风不是画面主体（「少年漫动感线条」「少年感」），
# 判定前先中性化，否则会把「辣妹」这种女性题材误判成男（实测案例 jm-7710200479195729214）。
STYLE_WORDS = re.compile(r"少年[漫感风气]|少女[漫感风气]")


def _neutralize(text):
    return STYLE_WORDS.sub("画风", str(text or ""))


def _has(text, words, en_words):
    for w in words:
        if w in text:
            return True
    for w in en_words:
        if re.search(r"\b" + w + r"\b", text, re.I):
            return True
    return False


def detect_gender(text):
    """返回 'F' / 'M' / ''。主语区（前 40 字）优先，其次全文。"""
    t = _neutralize(text)
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
            return ""
    return ""


def _strip_negative(body):
    b = str(body or "")
    b = re.split(r"--no\b|negative\s*prompt|负面提示词|负面词|\bno\s+(?:text|logo)", b, flags=re.I)[0]
    return b.strip()


def guess(title, prompt):
    """保守的文案判定 -> (portrait:int, gender:str)。认不出返回 (0, '')。"""
    title = _neutralize(title)
    body = _neutralize(_strip_negative(prompt))[:400]
    t40 = title[:40]
    head = body[:80]
    text = title + " " + body

    strong = bool(PERSON_STRONG.search(text))
    # 标题或以人物开头的正文里必须有明确主体词
    person = strong or bool(PERSON_WORD.search(t40)) or bool(PERSON_WORD.search(head))
    if not person:
        return 0, ""
    # 版式稿 / 商品 / 动物 / 多视角设定稿 -> 否决（除非有强人像术语）
    if not strong and (NOT_PERSON.search(t40) or NOT_PERSON.search(head)):
        return 0, ""
    if LAYOUT.search(text[:200]) and not strong:
        return 0, ""
    if MULTI.search(text):
        return 1, ""
    g = detect_gender(t40) or detect_gender(head)
    return 1, g


_cache = {"mtime": None, "data": {}}
_vcache = {"mtime": None, "data": {}}
_mcache = {"mtime": None, "data": {}}


def _load(path, cache):
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return {}
    if cache["mtime"] == mt:
        return cache["data"]
    try:
        d = json.load(open(path, encoding="utf-8"))
        cache["data"] = d if isinstance(d, dict) else {}
        cache["mtime"] = mt
    except Exception:
        cache["data"] = {}
    return cache["data"]


def load_labels():
    """人工逐张看图的标签（最高优先级）。"""
    return _load(LABELS, _cache)


def load_vision():
    """视觉模型打出的标签（第二优先级）。"""
    return _load(VISION, _vcache)


def load_model():
    """性别识别模型的高置信输出（第三优先级，只给性别）。"""
    return _load(MODEL, _mcache)


def label_for(rid, title, prompt):
    """人工 > 视觉模型 > 性别识别模型 > 文案兜底。"""
    lab = load_labels().get(rid)
    if isinstance(lab, dict):
        return int(lab.get("portrait") or 0), str(lab.get("gender") or "")
    vis = load_vision().get(rid)
    if isinstance(vis, dict):
        return int(vis.get("portrait") or 0), str(vis.get("gender") or "")
    p, g = guess(title, prompt)
    if not g:
        m = load_model().get(rid)
        if isinstance(m, dict) and m.get("gender") in ("F", "M"):
            # 性别识别模型只补性别；是否人像仍由文案层决定。
            g = m["gender"]
    return p, g

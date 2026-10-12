#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
来源相关配置集中在这里读取, 代码里不写死任何域名 / 密钥 / 账号。

取值顺序: 环境变量  >  同目录 secrets.json (本地开发用, 已在 .gitignore)

需要配置的键:
  SRC_BASE       数据来源的接口根地址
  SRC_AES_KEY    登录密码加密用的 AES 密钥
  SRC_PHONE      登录手机号
  SRC_PASS       登录密码
  IMG_HOST_I     图床主机一(代号 i)
  IMG_HOST_Q     图床主机二(代号 q)
  SRC_BANNED     逗号分隔的禁用词, 提示词里出现即丢弃该条
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

KEYS = ("SRC_BASE", "SRC_AES_KEY", "SRC_PHONE", "SRC_PASS",
        "IMG_HOST_I", "IMG_HOST_Q", "SRC_BANNED")


def load():
    cfg = {}
    p = os.path.join(HERE, "secrets.json")
    if os.path.exists(p):
        try:
            cfg.update(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    for k in KEYS:
        v = os.environ.get(k)
        if v:
            cfg[k] = v
    return cfg


CFG = load()

SRC_BASE = (CFG.get("SRC_BASE") or "").rstrip("/")
SRC_AES_KEY = CFG.get("SRC_AES_KEY") or ""
SRC_PHONE = CFG.get("SRC_PHONE") or ""
SRC_PASS = CFG.get("SRC_PASS") or ""

# 图床主机 -> 单字母代号(代号会写进站点数据, 主机名不会)
HOST_TOKEN = {}
for _host, _token in ((CFG.get("IMG_HOST_I"), "i"), (CFG.get("IMG_HOST_Q"), "q")):
    if _host:
        HOST_TOKEN[_host.strip().lower()] = _token

# 禁用词
BANNED = [w.strip() for w in (CFG.get("SRC_BANNED") or "").split(",") if w.strip()]


def leak_pattern():
    """构造"来源痕迹"正则: 任何链接 + 已配置的图床主机及其主域名 + 禁用词。"""
    parts = [r"https?://"]
    for h in HOST_TOKEN:
        labels = h.split(".")
        parts.append(re.escape(h))
        if len(labels) >= 2:
            parts.append(re.escape(labels[-2]))              # 主域名词干
            parts.append(re.escape(".".join(labels[-2:])))   # 主域名
    parts += [re.escape(w) for w in BANNED]
    return re.compile("|".join(parts), re.I)


LEAK_RE = leak_pattern()


def require(names):
    """检查必需配置是否齐全, 缺失则报错退出。"""
    missing = [n for n in names if not CFG.get(n)]
    if missing:
        raise SystemExit("!! 缺少配置: %s (设置环境变量或写入 %s/secrets.json)"
                         % (", ".join(missing), HERE))

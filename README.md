# 白日梦AI生成库

视频提示词 · 灵感画廊 · 文本提示词，纯静态站点，直接托管在 GitHub Pages。

| 标签 | 条数 |
| --- | --- |
| 灵感画廊 | 见 `data/manifest.json` 的 `galCount` |
| 视频提示词 | `videoCount` |
| 文本提示词 | `textCount` |

## 上线步骤

1. 新建一个 GitHub 仓库（Public），把本目录所有文件推上去。
2. 仓库 **Settings → Pages**，Source 选 `Deploy from a branch`，分支选 `main`、目录选 `/ (root)`，保存。
3. 等 1 分钟左右，访问 `https://<用户名>.github.io/<仓库名>/`。

仓库根目录已带 `.nojekyll`，避免 GitHub Pages 的 Jekyll 处理。

## 图片是怎么加载的

页面里的封面地址形如 `/m/i/xxxxxxxx.png`（`i`/`q` 是图床代号），
真实图床域名不在本仓库内，而是写在一个独立的图片代理里。
代理地址配置在 **`assets/js/config.js`**：

```js
window.SITE_CONFIG = { IMG_BASE: 'https://你的代理域名' };
```

换代理只需要改这一行。仓库里不含任何图床域名，也不需要图片映射表。
`IMG_FALLBACK` 是备用代理：主地址加载失败时，图片会自动回退过去再试一次。

## 每天自动刷新数据

`.github/workflows/refresh.yml` 会每天 04:30（北京时间）自动重抓一次并提交。

启用前需要在仓库 **Settings → Secrets and variables → Actions** 里加这些 Secret：

| Secret | 说明 |
| --- | --- |
| `SRC_BASE` | 数据来源的接口根地址 |
| `SRC_AES_KEY` | 登录密码加密用的 AES 密钥 |
| `SRC_PHONE` | 登录手机号 |
| `SRC_PASS` | 登录密码 |
| `SRC_BANNED` | 逗号分隔的禁用词，提示词里出现即丢弃该条 |
| `IMG_HOST_I` | 图床主机一 |
| `IMG_HOST_Q` | 图床主机二 |
| `IMG_HOST_V` | 视频/参考图主机（原样透传，不缩图） |

这些值都不写进代码，所以公开仓库里看不到任何来源信息。
也可以随时在 Actions 页面手动点 `Run workflow` 触发一次。

## 目录

```
index.html            页面骨架
assets/css            样式
assets/js/config.js   图片代理地址（唯一需要改的配置）
assets/js/app.js      前端逻辑
data/manifest.json    分类与计数
data/gal_*.json       灵感画廊分片
data/video_*.json     视频提示词分片
data/text_*.json      文本提示词分片
tools/                数据抓取与重建脚本（Actions 调用）
.github/workflows/    每日刷新工作流
```

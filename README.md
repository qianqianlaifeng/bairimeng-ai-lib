# 白日梦AI生成库 · 图片 & 视频提示词库

一个纯静态的提示词浏览站，包含：

- 图片提示词（分类浏览、搜索、复制）
- 视频提示词（封面 + 可直接播放的视频，悬停预览、点击查看全文）
- 文本提示词（结构化 / 中英对照）

## 本地预览

```bash
# 在项目根目录
python serve_free.py 8789
# 浏览器打开 http://127.0.0.1:8789/
```

`serve_free.py` 仅做 gzip 与本地托管，不依赖任何外部服务。

## 部署到 GitHub Pages

1. 在 GitHub 新建一个仓库（仓库名随意，例如 `bairimeng-ai`）。
   若要使用 `用户名.github.io` 形式，仓库名需为 `用户名.github.io`。
2. 进入本目录（`freesite/`），提交并推送（本仓库已初始化并提交，只需补远程与推送）：

   ```bash
   git branch -M main
   git remote add origin https://github.com/你的用户名/你的仓库名.git
   git push -u origin main
   ```
   > 若本地当前分支已是 `master`，上面的 `git branch -M main` 会把它重命名为 `main` 再推送。
   > 也可不改名，直接在 Pages 里选择 `master` 分支作为源。

3. 仓库 Settings → Pages → Source 选 `main`（或你实际推送的分支）分支、`/ (root)`，保存后等待构建。
4. 访问 `https://用户名.github.io/你的仓库名/` 即可。

> 本目录已包含 `.nojekyll`，确保 GitHub Pages 不忽略下划线开头的资源。
> 推送时 GitHub 可能要求身份验证：推荐用 **个人访问令牌（PAT）** 代替密码，
> 或配置 SSH key；也可安装 GitHub Desktop 一键发布。

## 关于媒体（图片 / 视频）显示

- **视频**：直接调用公开的视频 CDN 地址，无防盗链，浏览器可原生播放与悬停预览。
- **图片提示词配图**：部分原始图源已不可达，图片分类默认以分类渐变封面展示
  （保证不破图），不影响提示词文本的完整查看与复制。如需真实配图，
  可替换为其它可达图源后重新生成 `data/image.json`。

## 数据格式

`data/` 下的 `text.json` / `image.json` / `video.json` 为紧凑数组结构，由构建脚本生成。
`manifest.json` 汇总分类与计数。

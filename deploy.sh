#!/usr/bin/env bash
# 一键部署白日梦AI生成库 到 GitHub Pages
# 用法（在 Git Bash 里，进入 freesite/ 目录后执行）：
#   bash deploy.sh 你的GitHub用户名 你的仓库名
# 例：bash deploy.sh zhangsan bairimeng-ai
# 若要用 用户名.github.io 形式，仓库名就填 用户名.github.io
#
# 注意：推送时 GitHub 会要求身份验证，
#   - 密码处请填 个人访问令牌(PAT)，不要用账号密码
#   - 或提前配置好 SSH key

set -e

USER="$1"
REPO="$2"

if [ -z "$USER" ] || [ -z "$REPO" ]; then
  echo "用法: bash deploy.sh <GitHub用户名> <仓库名>"
  echo "示例: bash deploy.sh zhangsan bairimeng-ai"
  exit 1
fi

# 确保分支名为 main（GitHub Pages 默认常用）
git branch -M main

# 添加远程（已存在则更新）
if git remote | grep -q '^origin$'; then
  git remote set-url origin "https://github.com/$USER/$REPO.git"
else
  git remote add origin "https://github.com/$USER/$REPO.git"
fi

# 推送
git push -u origin main

echo ""
echo "✅ 推送完成！"
echo "请到仓库 Settings → Pages → Source 选择 main 分支、/ (root)，保存后等待构建。"
echo "访问地址：https://$USER.github.io/$REPO/"

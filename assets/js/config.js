/* 站点运行配置 —— 换图片代理只改这一个文件。 */
window.SITE_CONFIG = {
  /* 图片代理主地址(末尾不要带斜杠)。封面地址形如 "/m/i/xxx.png",
     会拼在这个地址后面。留空 = 同域(本地 node server.js 预览用)。
     换成你自己的代理后, 仓库里不需要任何图片映射表。 */
  IMG_BASE: 'https://img.fakashop.ccwu.cc',
  /* 备用代理: 主地址加载失败时, 图片自动回退到这里再试一次(留空 = 不回退) */
  IMG_FALLBACK: 'https://d32d01410fc8419ca589ae7dcb4b2059.sg2.agentos-app.run'
};

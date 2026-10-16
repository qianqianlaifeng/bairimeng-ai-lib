/* 站点运行配置。
   媒体地址现已全部是各图床的完整直连 URL(https://...), coverUrl() 会原样使用,
   不再需要图片代理前缀。IMG_BASE 仅作兼容保留: 若某天出现 /m/xxx 形式的相对
   路径, 才会拼这个前缀。留空 = 同域。

   IMG_SHRINK: 对"自身不支持缩图参数、原图又很大"的图床做二次缩图。
   这类图床返回的原图 ~245KB, 首屏 24 张要下 6MB, 且单张要等十几秒。
   走 Worker 代理后由 Cloudflare 侧(Worker 里的 cf.image)转 webp + 限宽 600px,
   单张降到 ~73KB、几百毫秒。只对 hosts 里列出的图床生效, 其余保持直连不动。
   注: 该 Worker 域名为老域名(国内放行); 新建的子域名实测会被 RST, 不要改。 */
window.SITE_CONFIG = {
  IMG_BASE: '',
  IMG_FALLBACK: '',
  /* data 版本号: data/manifest.json 的内容哈希。app.js 把它拼到每个
     data/*.json 请求后面(?v=), 数据一变 URL 就变, 击穿 GitHub Pages 的
     max-age=600 缓存, 避免用户拿到缺 wf 数据的旧 manifest。
     每日 Actions 刷新数据后也会同步重写这个值(见 refresh.yml)。 */
  DATA_VER: 'd4f964a7',
  IMG_SHRINK: {
    base: 'https://img.fakashop.ccwu.cc',
    tag: 'o',
    hosts: ['media.openimages.relakkesyang.org']
  }
};

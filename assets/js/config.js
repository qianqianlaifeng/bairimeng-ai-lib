/* 站点运行配置。
   媒体地址现已全部是各图床的完整直连 URL(https://...), coverUrl() 会原样使用,
   不再需要图片代理前缀。IMG_BASE 仅作兼容保留: 若某天出现 /m/xxx 形式的相对
   路径, 才会拼这个前缀。留空 = 同域。 */
window.SITE_CONFIG = {
  IMG_BASE: '',
  IMG_FALLBACK: ''
};

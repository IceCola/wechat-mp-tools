# 原始文章导出

设置中的“原始 Markdown”与“原始 HTML”默认勾选，已有设置缺少新字段时也默认开启原始 Markdown；已明确关闭原始 HTML 的设置仍保持关闭。

每篇文章可以同时生成：

- `日期_标题_raw.md`：原始正文的纯 Markdown，图片使用微信远程 URL，不经过内容过滤或本地图片替换。保留封面、标题、作者、公众号、北京时间；明确识别到原创标记时保留“原创”。
- `日期_标题_raw.html`：完整抓取页面，保留页头和脚本，激活懒加载图片；缺少页头时补上已知元信息。
- `日期_标题.md`：原有阅读版 Markdown，按照过滤规则和图片保存方式生成，默认使用本地图片。

“尝试加载精选留言”默认开启。如果抓取页面已包含留言则直接保存；否则使用现有 Chromium 抓取通道加载页面底部。微信可能要求登录态或限制访问，因此不保证能获取留言。是否获取到记录在 `metadata.json` 的 `comments_status` 和 `comments_warning`，获取到的留言与回复进入两种原始格式及 `data.json`。获取失败不会丢弃正文，也不会标记为“文章没有留言”。

## 离线补生成已有下载

```powershell
python -X utf8 scripts/backfill_raw_markdown.py "D:\Application\WeChat MP Tools re\data\1024"
```

从已保存的 `data.json` 正文（或 raw HTML）和元数据生成 `*_raw.md`，不联网，不修改已有 HTML 或阅读版 Markdown，不覆盖已存在的原始 Markdown。正文保留全部图片，不复用可能已过滤图片的阅读版。缺失的原创标记和留言不能离线恢复，留言状态记为 `unavailable_in_saved_files`。

源码修改不会自动更新已经打包安装的 EXE。源码运行可直接使用新选项；EXE 需按 `BUILD.md` 重新打包后使用。

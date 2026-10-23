# 本地开发与上游同步

本仓库的个人下载体验改造在 `dev` 分支进行。`main` 用于同步远端主分支，个人功能不直接提交到 main。

## 本次下载选项

在「系统设置 → 下载与存储配置」选择并保存，随后启动下载。文章下载和网址下载页面也有直达设置的按钮。

- 格式可多选：HTML、Markdown、PDF、纯文本、原始 HTML。只生成勾选的导出文件。新安装默认 HTML + Markdown，不默认生成 PDF、文本或原始 HTML；已有保存的 Markdown/PDF 开关继续有效。
- 图片可下载到 `media/`，或以 Base64 内嵌进 HTML/Markdown。需启用「自动下载文章图片」。关闭后保留在线图片链接。内嵌模式不留下独立图片文件；PDF 自身包含图片，原始 HTML 按定义保留在线图片链接。部分 Markdown 阅读器不显示 Base64 图片。
- 可给文章文件夹和导出文件加上 `YYYY-MM-DD_` 发布日期前缀，按北京时间计算。无法解析发布日期时仅使用标题，不用下载时间代替。正文标题和历史标题不会带上该前缀。
- `data.json`、`metadata.json` 是现有 RSS、上传和下载记录使用的数据文件，始终保留。只选文本或原始 HTML 时不额外下载图片/视频。
- 设置适用于之后的单篇、批量和 RSS 下载，不迁移已有文件。只导出 PDF 时的临时 HTML 会在转换后清理。未导出 HTML 的记录仍可从下载历史打开；Markdown/文本直接预览文本，PDF 使用浏览器预览。
- 对已下载文章重跑内容过滤仍只处理已有的清洗后 HTML，并更新已选择的文本文件；不会凭空补出未选择的导出格式。

## 合并远端更新

先保存或提交工作区改动，再执行：

```bash
git switch main
git pull --ff-only origin main
git switch dev
git merge main
```

如有冲突，在 dev 解决并验证后提交。不要通过强制重置 main 或 dev 来掩盖冲突。如果未来更换同步来源，将 `origin` 换成明确配置的上游 remote 名称；当前 remote 可用 `git remote -v` 查看。

需要将开发分支保存到远端时执行 `git push -u origin dev`。本次仅建立本地 dev 并修改、验证，不自动推送或发布。

## 本地验证

使用 Python 3.12 和项目依赖，在仓库根目录执行：

```bash
python -m unittest discover -s tests -p test_download_options.py -v
python -m unittest discover -s tests -p test_md_and_pdf.py -v
python -m unittest discover -s tests -p test_rss_avatars.py -v
```

新测试隔离文件与网络，验证格式选择、图片内嵌/本地引用、日期、同名文件保护、PDF 失败/临时文件清理、设置 API 校验内容重过滤时的格式选择，以及无 HTML 时的历史/RSS。既有 PDF 测试需本机安装 Chrome 或 Edge。

2026-10-23 开发机验证：上述三组共 32 项通过；另以真实 Chrome 验证仅导出 PDF 时包含本地图片且临时 HTML 已清理。使用真实 Chrome 检查设置页保存、重新加载、拒绝空格式选择和恢复默认，并检查设置页截图。微信登录、历史列表及真实账号下载没有重跑；Windows 未做本次实际运行验证。

<p align="right"><a href="README_EN.md">English</a> | <strong>中文</strong></p>

<h1 align="center">Save My RedNote 🍠</h1>

<p align="center">备份你的小红书笔记，支持本地预览和 Cloudflare Pages 部署。</p>

<blockquote>如果你的小红书账号被封，这些笔记将是你唯一的回忆。</blockquote>

---

## 快速开始

```bash
git clone git@github.com:hugcosmos/SaveMyRedNote.git
cd SaveMyRedNote
pip install Pillow
```

准备：
- Chrome 安装 [BrowserSkill 扩展](https://chromewebstore.google.com/detail/browserskill/hhcmgoofomhgciiibhipgmgkgnoenaoi)
- 安装 `bsk` CLI（[官方指南](https://github.com/Tencent/BrowserSkill)）
- Chrome 登录 xiaohongshu.com
- 确认 `bsk session list` 能列出你的浏览器

### 获取 Cookie

```bash
python3 xhs_collect.py auth SESSION_ID
```

按提示从 Chrome F12 → Network 复制粘贴 Cookie。

### 一键跑完

```bash
python3 xhs_collect.py run-all SESSION_ID
```

脚本会自动完成：抓笔记 → 下载图片 → 添加水印 → 生成展示页。

> ⚠️ 如果账号曾被封禁，用户名/头像/简介会被重置。在 `admin.html` 中修正。

### 本地预览

```bash
python3 xhs_collect.py serve
```

访问 http://localhost:8088

---

## 配置

方式一：脚本自动生成 `config.json`。\
方式二：`admin.html` 页面配置（存浏览器 localStorage）。\
方式三：`index.html` 内 DEFAULTS（硬编码，所有访客可见）。

优先级：**localStorage(admin) > config.json > DEFAULTS**

### AI 翻译

```bash
export AGNES_API_KEY=sk-your-key
python3 xhs_collect.py translate
```

需要从 [Agnes AI](https://agnes-ai.com) 获取 API Key。不配不影响页面展示。

---

## 部署到 Cloudflare

```bash
python3 xhs_collect.py build
```

上传以下文件到 Cloudflare Pages：

```
index.html  data.js  manifest.json  images_wm/
```

不需要 build 命令，纯静态文件。

---

## 命令

| 命令 | 说明 |
|------|------|
| `auth SESSION` | 粘贴 Cookie |
| `list SESSION` | 抓取笔记列表 + 用户资料 |
| `extract` | 批量提取笔记详情 |
| `images` | 下载原图 |
| `comments SESSION` | 提取评论（默认仅作者） |
| `comments SESSION --full` | 提取全部评论 |
| `watermark` | 添加水印 |
| `translate` | AI 翻译（需 AGNES_API_KEY） |
| `build` | 生成展示页 |
| `serve` | 本地预览 |
| `run-all SESSION` | 全自动流程 |

---

## 依赖

| 组件 | 用途 | 许可证 |
|------|------|--------|
| [Pillow](https://python-pillow.org) | 图片水印 | [Historical](https://github.com/python-pillow/Pillow/blob/main/LICENSE)（MIT 兼容） |
| [BrowserSkill](https://github.com/Tencent/BrowserSkill) | 浏览器自动化 | MIT |
| Python 标准库 | — | PSF |

---

## 隐私

默认模式只保存你的帖子和你的回复，**其他用户的信息均不保存**。
CDN 链接在构建时自动剔除。API Key 和 Cookie 不在展示页。

---

## License

MIT. Copyright (c) 2026 Nicky

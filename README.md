<p align="right"><a href="README_EN.md">English</a> | <strong>中文</strong></p>

<h1 align="center">Save My RedNote</h1>

<p align="center">备份你的小红书笔记，支持本地预览和 Cloudflare Pages 部署。</p>

> 如果你的小红书账号被封，这些笔记将是你唯一的回忆。

---

## ⚠️ 免责声明

本工具仅供个人备份用途。**默认模式只存储你本人的帖子和作为作者的回复，其他用户的信息均不保存。** 请尊重他人隐私和数据版权。

---

## 快速开始

```bash
git clone git@github.com:hugcosmos/SaveMyRedNote.git
cd SaveMyRedNote
pip install Pillow
```

**前置准备：**
- Chrome 安装 [BrowserSkill 扩展](https://chromewebstore.google.com/detail/browserskill/hhcmgoofomhgciiibhipgmgkgnoenaoi)
- 安装 `bsk` CLI（[官方指南](https://github.com/Tencent/BrowserSkill)）
- Chrome 登录 xiaohongshu.com
- 确认 `bsk session list` 能列出你的浏览器

### 1. 获取 Cookie

```bash
python3 xhs_collect.py auth SESSION_ID
```

从 Chrome F12 → Network → 复制 Cookie 粘贴到终端。

### 2. 一键跑完

```bash
python3 xhs_collect.py run-all SESSION_ID
```

脚本自动完成：抓笔记 → 下载图片 → 水印 → 生成展示页。

> ⚠️ 账号被封后，用户名/头像/简介会被平台重置。用 `admin.html` 修正。

### 3. 本地预览

```bash
python3 xhs_collect.py serve
```

打开 http://localhost:8088

---

## 配置

三种方式，优先级：**admin(localStorage) > config.json > DEFAULTS**

**config.json** — 脚本自动生成：

```json
{ "authorName": "你的用户名", "authorUserId": "你的用户ID", ... }
```

**admin.html** — 浏览器页面可视化配置，存你自己的 localStorage。

**DEFAULTS** — `index.html` 中硬编码，所有人可见。

### AI 翻译（可选）

```bash
export AGNES_API_KEY=sk-your-key
python3 xhs_collect.py translate
```

不配置则只翻译页面 UI 文字（首页→Home 等），笔记标题、正文、评论仍为中文。

---

## 部署到 Cloudflare

```bash
python3 xhs_collect.py build
```

上传以下文件到 Cloudflare Pages：

```
index.html  data.js  manifest.json  images_wm/
```

---

## 命令

| 命令 | 说明 |
|------|------|
| `auth SESSION` | 粘贴 Cookie |
| `list SESSION` | 抓取笔记列表 + 用户资料 |
| `extract` | 批量提取笔记详情 |
| `images` | 下载原图 |
| `comments SESSION` | 提取评论（默认仅作者） |
| `comments --full` | 提取全部评论 |
| `watermark` | 添加水印 |
| `translate` | AI 翻译（需 API Key） |
| `build` | 生成展示页 |
| `serve` | 本地预览 |
| `run-all SESSION` | 全自动流程 |

---

## 获取的数据

| 数据 | 默认 | `--full` 模式 |
|------|------|---------------|
| 你的笔记内容 | ✅ 保存 | ✅ 保存 |
| 你本人的评论 | ✅ 保存 | ✅ 保存 |
| 你的回复 | ✅ 保存 | ✅ 保存 |
| 他人的评论 | ❌ 不保存 | ✅ 保存 |
| 他人的头像/昵称/ID | ❌ 不保存 | ✅ 保存 |
| 图片 CDN 链接 | ❌ 构建时剔除 | ❌ 构建时剔除 |
| API Key / Cookie | ❌ 不在展示页 | ❌ 不在展示页 |
| 你的配置 | 在 .gitignore 中 | — |

---

## License

[MIT](LICENSE)。Copyright (c) 2026 Nicky

| 依赖 | 许可证 | 兼容 |
|------|--------|------|
| Pillow | [Historical](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | ✅ MIT 兼容 |
| BrowserSkill | [MIT](https://github.com/Tencent/BrowserSkill/blob/main/LICENSE) | ✅ |
| Python 标准库 | [PSF](https://docs.python.org/3/license.html) | ✅ |

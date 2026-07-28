<p align="right">
  <a href="README_EN.md">English</a> | <strong>中文</strong>
</p>

<h1 align="center">Save My RedNote 🍠</h1>

<p align="center">备份你的小红书笔记到本地，支持本地预览和 Cloudflare Pages 部署。</p>

<blockquote>
<p><strong>如果你的小红书账号被封，这些笔记将是你唯一的回忆。</strong></p>
</blockquote>

---

## ⚠️ 免责声明

本工具仅供个人备份用途。**默认模式只存储你本人的帖子和作为作者的回复，其他用户的信息均不保存。** 请尊重他人隐私和数据版权。

---

## ✨ 功能

- 📋 一键抓取笔记列表、详情、图片
- 🖼️ 自定义水印
- 💬 评论备份（默认仅作者本人）
- 🌐 本地预览 + Cloudflare 部署
- 🌗 深色模式
- 🌏 中英文切换
- 🔒 CDN 链接构建时自动剔除

---

## 📦 依赖

| 名称 | 用途 | 许可证 |
|------|------|--------|
| [Pillow](https://python-pillow.org) | 图片水印 | [Historical](https://github.com/python-pillow/Pillow/blob/main/LICENSE)（MIT 兼容） |
| [BrowserSkill (bsk)](https://github.com/Tencent/BrowserSkill) | 浏览器自动化 | [MIT](https://github.com/Tencent/BrowserSkill/blob/main/LICENSE) |

翻译脚本仅使用 Python 标准库，无需额外安装。

---

## 🚀 快速开始

### 0. 前置准备

1. Chrome 安装 [BrowserSkill 扩展](https://chromewebstore.google.com/detail/browserskill/hhcmgoofomhgciiibhipgmgkgnoenaoi)
2. 安装 `bsk` CLI（[官方指南](https://github.com/Tencent/BrowserSkill)）
3. Chrome 登录 [xiaohongshu.com](https://www.xiaohongshu.com)
4. 确认 `bsk session list` 能列出你的浏览器

### 1. 安装 Python 依赖

```bash
pip install Pillow
```

### 2. 获取 Cookie（一次性）

```bash
python3 xhs_collect.py auth SESSION_ID
```

**为什么不能自动获取？** 小红书的登录 Cookie 标记为 `httpOnly`，JavaScript 无法读取，bsk 也无法获取。

**正确步骤：**
1. Chrome 按 F12 → Network 标签
2. 刷新页面，点击第一个网络请求
3. 在 Request Headers 找到 `Cookie:` 行 → 右键 "Copy value"
4. 粘贴到终端

### 3. 抓取笔记列表（自动提取用户资料）

```bash
python3 xhs_collect.py list SESSION_ID
```

脚本会自动抓取你的昵称、头像、简介等信息写入 `config.json`。

> ⚠️ **封禁账号注意：** 如果账号曾被封禁，小红书会重置你的用户名、头像和简介。`list` 抓到的信息可能是重置后的值。请用 `admin.html` 修正回你原本的信息。

### 4. 批量提取笔记详情

```bash
python3 xhs_collect.py extract
```

### 5. 下载图片

```bash
python3 xhs_collect.py images
```

### 6. 添加水印

```bash
python3 xhs_collect.py watermark
python3 xhs_collect.py watermark --text "你的昵称" --force
```

### 7. 生成展示页

```bash
python3 xhs_collect.py build
```

### 8. 本地预览

```bash
python3 xhs_collect.py serve
```

打开 http://localhost:8088

### 一键跑完

```bash
python3 xhs_collect.py run-all SESSION_ID
```

---

## 🌤️ 部署到 Cloudflare

生成 `data.js` 和 `images_wm/` 之后：

1. Cloudflare Dashboard → **Pages** → **创建项目** → **直接上传**
2. 上传以下文件：

```
index.html
data.js
manifest.json
images_wm/       ← 整个文件夹
```

3. **不需要 build 命令**，直接部署

> 不需要上传 `admin.html`、`.py` 文件、`images/`。

---

## ⚙️ 配置

### config.json

```json
{
  "watermarkText": "你的昵称",
  "authorName": "你的用户名",
  "authorUserId": "你的用户ID",
  "authorRedId": "你的小红书号",
  "authorIp": "你的IP属地",
  "authorAvatar": "images_wm/xxx/01.webp",
  "authorBio": "你的简介"
}
```

| 字段 | 用途 | 必须？ |
|------|------|--------|
| `watermarkText` | 水印文字 | 可选 |
| `authorName` | 页面显示的用户名 | 推荐 |
| `authorUserId` | 用于评论中识别你 | list/comments 必须 |
| `authorRedId` | 小红书号 | 可选 |
| `authorIp` | IP 属地 | 可选 |
| `authorAvatar` | 头像路径 | 可选 |
| `authorBio` | 个人简介 | 可选 |

### AI 翻译

```bash
export AGNES_API_KEY=sk-your-key
python3 xhs_collect.py translate
```

API Key 从 [Agnes AI](https://agnes-ai.com) 获取。不配置不影响页面展示。

### 侧边栏链接

编辑 `index.html` 中 `DEFAULTS.sidebarLinks` 数组，重新部署。

---

## 📖 命令参考

| 命令 | 说明 |
|------|------|
| `auth SESSION` | 手动粘贴 Cookie |
| `list SESSION` | 抓取笔记列表 |
| `extract` | 批量提取笔记详情 |
| `images` | 下载原图 |
| `comments SESSION` | 提取评论（默认仅作者） |
| `comments SESSION --full` | 提取全部评论 |
| `watermark` | 批量水印 |
| `watermark --text X --force` | 自定义水印并覆盖 |
| `translate` | AI 翻译（需 AGNES_API_KEY） |
| `build` | 生成 data.js |
| `serve` | 本地预览（8088） |
| `update SESSION` | 增量更新 |
| `run-all SESSION` | 全自动流程 |

---

## 🔒 隐私说明

| 数据 | 默认 | `--full` 模式 |
|------|------|---------------|
| 你的笔记内容 | ✅ 保存 | ✅ 保存 |
| 你本人的评论 | ✅ 保存 | ✅ 保存 |
| 你的回复 | ✅ 保存 | ✅ 保存 |
| 他人的评论 | ❌ 不保存 | ✅ 保存 |
| 他人的头像/昵称/ID | ❌ 不保存 | ✅ 保存 |
| 图片 CDN 链接 | ❌ 构建时剔除 | ❌ 构建时剔除 |
| API Key / Cookie | ❌ 不在展示页 | ❌ 不在展示页 |

---

## 🛡️ 许可证

MIT License。`Copyright (c) 2026 Nicky`

| 依赖 | 许可证 | MIT 兼容？ |
|------|--------|-----------|
| 本项目 | [MIT](LICENSE) | — |
| Pillow | Historical License | ✅ |
| BrowserSkill (bsk) | MIT | ✅ |
| Python 标准库 | PSF License | ✅ |

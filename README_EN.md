<p align="right">
  <strong>English</strong> | <a href="README.md">中文</a>
</p>

<h1 align="center">Save My RedNote 🍠</h1>

<p align="center">Backup your Xiaohongshu notes locally with preview & Cloudflare Pages deployment.</p>

<blockquote>
<p><strong>If your Xiaohongshu account ever gets suspended, these notes are your only memory.</strong></p>
</blockquote>

---

## ⚠️ Disclaimer

For personal backup only. **Default mode stores only your own posts and your author replies — no other user data is saved.** Respect others' privacy and copyright.

---

## ✨ Features

- 📋 One-click fetch all notes, details, images
- 🖼️ Custom watermark
- 💬 Comment backup (author-only by default)
- 🌐 Local preview + Cloudflare Pages deploy
- 🌗 Dark mode
- 🌏 Chinese/English toggle
- 🔒 CDN URLs stripped at build time

---

## 📦 Dependencies

| Name | Purpose | License |
|------|---------|---------|
| [Pillow](https://python-pillow.org) | Watermark | [Historical](https://github.com/python-pillow/Pillow/blob/main/LICENSE) (MIT-compatible) |
| [BrowserSkill (bsk)](https://github.com/Tencent/BrowserSkill) | Browser automation | [MIT](https://github.com/Tencent/BrowserSkill/blob/main/LICENSE) |

The translation script uses only Python standard library — no extra install needed.

---

## 🚀 Quick Start

### 0. Prerequisites

1. Install the [BrowserSkill extension](https://chromewebstore.google.com/detail/browserskill/hhcmgoofomhgciiibhipgmgkgnoenaoi) in Chrome
2. Install the `bsk` CLI ([official guide](https://github.com/Tencent/BrowserSkill))
3. Log in to [xiaohongshu.com](https://www.xiaohongshu.com) in Chrome
4. Verify `bsk session list` shows your browser

### 1. Install Python dependency

```bash
pip install Pillow
```

### 2. Get Cookie (one-time)

```bash
python3 xhs_collect.py auth SESSION_ID
```

**Why manual?** Xiaohongshu marks its login cookie as `httpOnly`, so JavaScript (and thus bsk) can't read it.

**Steps:**
1. Chrome: F12 → Network tab
2. Refresh the page, click the first request
3. Find the `Cookie:` line in Request Headers → right-click "Copy value"
4. Paste into terminal

### 3. Fetch note list (auto-extracts profile)

```bash
python3 xhs_collect.py list SESSION_ID
```

The script auto-extracts your nickname, avatar, bio and writes to `config.json`.

> ⚠️ **Banned account:** Xiaohongshu resets your name/avatar/bio if your account was banned. Use `admin.html` to fix them.

### 4. Extract note details

```bash
python3 xhs_collect.py extract
```

### 5. Download images

```bash
python3 xhs_collect.py images
```

### 6. Add watermark

```bash
python3 xhs_collect.py watermark
python3 xhs_collect.py watermark --text "Your Name" --force
```

### 7. Build preview page

```bash
python3 xhs_collect.py build
```

### 8. Preview locally

```bash
python3 xhs_collect.py serve
```

Open http://localhost:8088

### One command to run all

```bash
python3 xhs_collect.py run-all SESSION_ID
```

---

## 🌤️ Deploy to Cloudflare

After generating `data.js` and `images_wm/`:

1. Go to Cloudflare Dashboard → **Pages** → **Create project** → **Direct upload**
2. Upload these files:

```
index.html
data.js
manifest.json
images_wm/       ← entire folder
```

3. **No build command needed**, just deploy

> Don't upload `admin.html`, `.py` files, or `images/`.

---

## ⚙️ Configuration

### config.json

```json
{
  "watermarkText": "Your Name",
  "authorName": "Your Name",
  "authorUserId": "your_user_id",
  "authorRedId": "your_red_id",
  "authorIp": "City",
  "authorAvatar": "images_wm/xxx/01.webp",
  "authorBio": "Your bio"
}
```

| Field | Purpose | Required |
|-------|---------|----------|
| `watermarkText` | Watermark text | Optional |
| `authorName` | Display name | Recommended |
| `authorUserId` | Identify you in comments | Required for list/comments |
| `authorRedId` | Xiaohongshu ID | Optional |
| `authorIp` | IP location | Optional |
| `authorAvatar` | Avatar path | Optional |
| `authorBio` | Bio text | Optional |

### AI Translation

```bash
export AGNES_API_KEY=sk-your-key
python3 xhs_collect.py translate
```

Get an API key from [Agnes AI](https://agnes-ai.com). Without it, the page still works — English version will just be unavailable.

### Sidebar links

Edit `DEFAULTS.sidebarLinks` in `index.html` and redeploy.

---

## 📖 Command Reference

| Command | Description |
|---------|-------------|
| `auth SESSION` | Paste cookie manually |
| `list SESSION` | Fetch note list |
| `extract` | Bulk extract note details |
| `images` | Download original images |
| `comments SESSION` | Extract comments (author-only) |
| `comments SESSION --full` | Extract all comments |
| `watermark` | Add watermarks |
| `watermark --text X --force` | Custom text & overwrite |
| `translate` | AI translate (needs AGNES_API_KEY) |
| `build` | Generate data.js |
| `serve` | Local preview (port 8088) |
| `update SESSION` | Incremental update |
| `run-all SESSION` | Full automated pipeline |

---

## 🔒 Privacy

| Data | Default | `--full` mode |
|------|---------|---------------|
| Your notes | ✅ Saved | ✅ Saved |
| Your comments | ✅ Saved | ✅ Saved |
| Your replies | ✅ Saved | ✅ Saved |
| Others' comments | ❌ Not saved | ✅ Saved |
| Others' avatars/names/IDs | ❌ Not saved | ✅ Saved |
| Image CDN URLs | ❌ Stripped at build | ❌ Stripped at build |
| API Key / Cookie | ❌ Not in preview page | ❌ Not in preview page |

---

## 🛡️ License

MIT License. `Copyright (c) 2026 Nicky`

| Dependency | License | MIT-compatible? |
|---|---|---|
| This project | [MIT](LICENSE) | — |
| Pillow | Historical License | ✅ |
| BrowserSkill (bsk) | MIT | ✅ |
| Python stdlib | PSF License | ✅ |

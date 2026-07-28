#!/usr/bin/env python3
"""
xhs_collect.py — 小红书数据采集 & 本地备份，一站式脚本。

═══════════════════════════════════════════════════════════════
依赖
═══════════════════════════════════════════════════════════════
  bsk (browser-skill CLI)   — Chrome 扩展，浏览器自动化 & cookie 提取
  curl                       — 高性能 HTTP 请求（笔记详情、图片下载）
  Pillow                     — pip install Pillow（图片水印）
  python3                    — 标准库，无需额外安装
  translate_data.py          — 同目录下的独立翻译脚本，需 AGNES_API_KEY 环境变量

前置条件
═══════════════════════════════════════════════════════════════
  1. Chrome 已安装 browser-skill 扩展且 bsk 在 PATH 中
  2. Chrome 已登录 xiaohongshu.com
  3. HTTP 代理运行在 127.0.0.1:7897（图片下载需要，可配置跳过）

用法
═══════════════════════════════════════════════════════════════
  python3 xhs_collect.py auth SESSION       浏览器登录态提取（cookie + 用户信息）
  python3 xhs_collect.py list SESSION        抓取所有笔记列表
  python3 xhs_collect.py extract             从笔记列表提取详情（curl 加速）
  python3 xhs_collect.py images              下载所有原图
  python3 xhs_collect.py comments SESSION    抓取评论（默认只抓作者本人）
  python3 xhs_collect.py comments SESSION --full  抓取全部评论（含他人）
  python3 xhs_collect.py watermark           批量添加水印
  python3 xhs_collect.py translate           调用 AI 翻译中文→英文
  python3 xhs_collect.py build               从 data/*.json 重新生成 data.js
  python3 xhs_collect.py serve               启动本地预览 (localhost:8088)

  python3 xhs_collect.py update SESSION      增量更新（extract + images + comments + build）
  python3 xhs_collect.py run-all SESSION     从零到部署的完整流程
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent

# ── Configuration ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = SCRIPT_DIR
DATA_DIR = BACKUP_DIR / "data"
IMAGES_DIR = BACKUP_DIR / "images"
IMAGES_WM_DIR = BACKUP_DIR / "images_wm"
COOKIE_FILE = Path("/tmp/xhs_cookie.txt")
NOTES_FILE = Path("/tmp/xhs_notes.json")
CONFIG_FILE = BACKUP_DIR / "config.json"
PROXY = os.environ.get("XHS_PROXY", "http://127.0.0.1:7897")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

# JS template for extracting note detail + comments from a note page
EXTRACT_JS = """(function(){
  var mapRef = window.__INITIAL_STATE__.note.noteDetailMap;
  var map = mapRef._rawValue || mapRef._value || mapRef;
  for (var k in map) {
    var entry = map[k];
    var e = entry._rawValue || entry._value || entry;
    var note = (e.note && (e.note._rawValue || e.note._value || e.note)) || e;
    if (note.noteId) {
      var imgs = (note.imageList||[]).map(function(img){ return {url:img.urlDefault||img.urlPre||'',width:img.width||0,height:img.height||0,fileId:img.fileId||''}; });
      var inter = note.interactInfo||{};
      var cmtsRaw = e.comments;
      var cmts = cmtsRaw._rawValue || cmtsRaw._value || cmtsRaw;
      var list = (cmts && cmts.list) || [];
      var comments = list.map(function(c){
        var cc = c._rawValue || c._value || c;
        var subs = (cc.subComments||[]).map(function(s){
          var ss = s._rawValue || s._value || s;
          return { id:ss.id, content:ss.content, likeCount:ss.likeCount, createTime:ss.createTime,
            ipLocation:ss.ipLocation,
            userInfo:{ userId:(ss.userInfo||{}).userId||'', nickname:(ss.userInfo||{}).nickname||'', image:(ss.userInfo||{}).image||'' } };
        });
        return { id:cc.id, content:cc.content, likeCount:cc.likeCount, createTime:cc.createTime,
          ipLocation:cc.ipLocation,
          userInfo:{ userId:(cc.userInfo||{}).userId||'', nickname:(cc.userInfo||{}).nickname||'', image:(cc.userInfo||{}).image||'' },
          subComments: subs, subCommentCount: cc.subCommentCount };
      });
      return JSON.stringify({
        noteId: note.noteId, title: note.title||'', description: note.desc||'',
        ipLocation: note.ipLocation||'', tags: (note.tagList||[]).map(function(t){return t.name||''}),
        timestamp: note.time||0,
        interactInfo: { likeCount: inter.likedCount||'0', collectCount: inter.collectedCount||'0', commentCount: inter.commentCount||'0', shareCount: inter.shareCount||'0' },
        images: imgs, _comments_raw: comments
      });
    }
  }
  return 'null';
})()"""
BSK_PATH = os.path.expanduser("~/.local/bin")
os.environ["PATH"] = f"{BSK_PATH}:{os.environ.get('PATH', '')}"

# ── Utilities ──────────────────────────────────────────────

def load_config():
    """Load user config from config.json, fallback to defaults."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}

def save_config(cfg):
    """Save user config."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def load_notes_list():
    """Load note ID list from /tmp/xhs_notes.json."""
    if not NOTES_FILE.exists():
        print("❌ 笔记列表文件不存在: /tmp/xhs_notes.json")
        print("   先运行: xhs_collect.py list SESSION")
        sys.exit(1)
    return json.loads(NOTES_FILE.read_text())

def load_cookie():
    """Load cookie string for curl."""
    if not COOKIE_FILE.exists():
        print("❌ Cookie 文件不存在: /tmp/xhs_cookie.txt")
        print("   先运行: xhs_collect.py auth SESSION")
        sys.exit(1)
    return COOKIE_FILE.read_text().strip()

def bsk_eval(session, expr, timeout=30):
    """Execute JS in browser via bsk evaluate."""
    cmd = ["bsk", "evaluate", "--session", session, expr]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""

def curl_fetch(url, cookie=None, timeout=30, follow=True):
    """Fetch URL via curl. Returns (body, status_code)."""
    cmd = ["curl", "-s", "-w", "\n__HTTP_STATUS__:%{http_code}", "--max-time", str(timeout)]
    if cookie:
        cmd += ["-b", cookie]
    if follow:
        cmd += ["-L"]
    cmd += ["-H", f"User-Agent: {UA}"]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        output = r.stdout
        # Split: body is everything before __HTTP_STATUS__:NNN
        if "__HTTP_STATUS__:" in output:
            parts = output.rsplit("__HTTP_STATUS__:", 1)
            body = parts[0].rstrip("\n")
            status = int(parts[1].strip() or "0")
        else:
            body = output
            status = 0
        return body, status
    except subprocess.TimeoutExpired:
        return "", 0

def curl_download(url, filepath, cookie=None, timeout=60):
    """Download a file via curl. Returns True on success."""
    if Path(filepath).exists() and Path(filepath).stat().st_size > 1000:
        return True  # already downloaded

    cmd = ["curl", "-s", "-x", PROXY, "-o", str(filepath), "--max-time", str(timeout)]
    if cookie:
        cmd += ["-b", cookie]
    cmd += ["-H", f"User-Agent: {UA}"]
    cmd.append(url)

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
        return r.returncode == 0 and Path(filepath).stat().st_size > 1000
    except Exception:
        if Path(filepath).exists():
            Path(filepath).unlink()
        return False

def safe_filename(text, note_id, index=0):
    """Generate a safe filename from title and noteId."""
    safe = re.sub(r'[<>:"/\\|?*]', '_', text[:50]) if text else f"note_{index:03d}"
    safe = safe.strip() or f"note_{index:03d}"
    return f"{index:03d}_{safe}_{note_id}"

def unwrap_vue(obj):
    """Extract _rawValue from Vue 3 reactive refs, recursively."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        if "_rawValue" in obj:
            return unwrap_vue(obj["_rawValue"])
        if "_value" in obj:
            return unwrap_vue(obj["_value"])
    return obj

def unwrap_state(js_expr):
    """Generate JS that unwraps Vue 3 refs before JSON.stringify."""
    return (
        "(function(){"
        "function uw(v){if(v===null||v===undefined)return v;"
        "if(v._rawValue!==undefined)return uw(v._rawValue);"
        "if(v._value!==undefined)return uw(v._value);"
        "return v;}"
        f"var data={js_expr};"
        "return JSON.stringify(uw(data));"
        "})()"
    )

def parse_note_state(raw_json_str):
    raw = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', raw_json_str)
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return None

    note_map = state.get("note", {}).get("noteDetailMap", {})
    for key in note_map:
        entry = note_map[key]
        if isinstance(entry, dict):
            note = entry.get("note", entry)
            if note.get("noteId"):
                # Images
                images = []
                for img in note.get("imageList", []):
                    images.append({
                        "url": img.get("urlDefault", "") or img.get("urlPre", ""),
                        "width": img.get("width", 0),
                        "height": img.get("height", 0),
                        "fileId": img.get("fileId", ""),
                    })

                inter = note.get("interactInfo", {})
                return {
                    "noteId": note.get("noteId"),
                    "title": note.get("title", ""),
                    "description": note.get("desc", ""),
                    "ipLocation": note.get("ipLocation", ""),
                    "tags": [t.get("name", "") for t in note.get("tagList", [])],
                    "timestamp": note.get("time", 0),
                    "interactInfo": {
                        "likeCount": inter.get("likedCount", "0"),
                        "collectCount": inter.get("collectedCount", "0"),
                        "commentCount": inter.get("commentCount", "0"),
                        "shareCount": inter.get("shareCount", "0"),
                    },
                    "images": images,
                }
    return None


# ═══ Step: auth ═════════════════════════════════════════════

def cmd_auth(session=None):
    """提示从浏览器复制完整 cookie，存入 /tmp/xhs_cookie.txt。"""
    print("🔐 需要你的小红书登录 cookie")
    print()
    print("步骤：")
    print("  1. 打开 Chrome，访问 www.xiaohongshu.com（确保已登录）")
    print("  2. 按 F12 → Network → 刷新页面 → 点第一个请求")
    print("  3. 在 Request Headers 里找到 'Cookie:' 那一行，右键 Copy value")
    print("  4. 粘贴到这里：")
    print()
    cookie = input("Paste full cookie > ").strip()
    if not cookie or len(cookie) < 100:
        print("❌ Cookie 太短，请确保复制完整")
        sys.exit(1)
    COOKIE_FILE.write_text(cookie)
    print(f"   ✅ cookie → {COOKIE_FILE} ({len(cookie)} chars)")

    # Save config placeholder
    cfg = load_config()
    cfg.setdefault("authorUserId", "")
    cfg.setdefault("authorName", "")
    save_config(cfg)
    print("   ⚠️ userId 和 nickname 请在 admin.html 中手动配置，或运行 auth-bsk")


# ═══ Step: list ═════════════════════════════════════════════

def cmd_list(session):
    """抓取笔记列表（所有已发布笔记的 id + xsecToken）。"""
    print("📋 抓取笔记列表...")

    config = load_config()
    user_id = config.get("authorUserId", "")
    if not user_id:
        print("❌ 未知用户 ID，先运行 auth 步骤或手动配置 admin.html")
        sys.exit(1)

    # Navigate to user's notes tab
    profile_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
    bsk_eval(session, f"location.href='{profile_url}'")
    time.sleep(4)

    # Extract user profile info from page state
    prof_js = """(function(){
      var uw=function(v){if(!v||!v._rawValue)return v;return uw(v._rawValue)};
      var u=uw(window.__INITIAL_STATE__.user);
      var info=uw(u.userInfo||u.user||{});
      return JSON.stringify({
        nickname: info.nickname||'', avatar: info.avatar||info.images||'',
        desc: info.desc||'', redId: info.redId||'', ipLocation: info.ipLocation||'',
        follows: info.follows||info.followCount||info.followingCount||'',
        fans: info.fans||info.fansCount||info.followerCount||''
      });
    })()"""
    profile_raw = bsk_eval(session, prof_js, timeout=10)
    try:
        prof = json.loads(profile_raw)
        if prof.get("nickname"):
            config["authorName"] = prof["nickname"]
            config["authorAvatar"] = prof.get("avatar", "")
            config["authorBio"] = prof.get("desc", "")
            config["authorRedId"] = prof.get("redId", "")
            config["authorIp"] = prof.get("ipLocation", "")
            config["followCount"] = prof.get("follows", "-")
            config["fansCount"] = prof.get("fans", "-")
            config["watermarkText"] = config.get("watermarkText") or prof["nickname"]
            if not config.get("sidebarLinks"):
                config["sidebarLinks"] = [
                    {"icon":"","nameZh":"微信","nameEn":"WeChat","url":""},
                    {"icon":"","nameZh":"头条","nameEn":"Toutiao","url":""},
                    {"icon":"","nameZh":"B站","nameEn":"Bilibili","url":""},
                    {"icon":"","nameZh":"视频号","nameEn":"Video","url":""},
                    {"icon":"","nameZh":"邮箱","nameEn":"Email","url":""},
                ]
            save_config(config)
            print(f"   👤 {prof['nickname']} | 📍 {prof.get('ipLocation','?')}")
            print(f"   ⚠️  若账号曾被封禁，用户名/头像/简介会被平台重置，请用 admin 页面修正")
    except Exception:
        print("   ⚠️ 未能提取用户资料（可在 admin 页面手动配置）")

    # Scroll to load all notes (up to 20 scrolls)
    for i in range(20):
        bsk_eval(session, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)

    # Extract notes from Vue state — XHS stores notes in nested batch objects.
    # Each batch key is a page index, each item key within a batch is a note index.
    # We flatten batches and deduplicate by noteId.
    js = """(function(){
  var notesRef = window.__INITIAL_STATE__.user.notes;
  var batches = notesRef._rawValue || notesRef._value || notes;
  var seen = {};
  var result = [];
  var batchKeys = Object.keys(batches).filter(function(k) { return !isNaN(k); });
  for (var bi = 0; bi < batchKeys.length; bi++) {
    var batch = batches[batchKeys[bi]];
    var batchData = batch._rawValue || batch._value || batch;
    var itemKeys = Object.keys(batchData).filter(function(k) { return !isNaN(k); });
    for (var ii = 0; ii < itemKeys.length; ii++) {
      var itemRaw = batchData[itemKeys[ii]];
      var n = itemRaw._rawValue || itemRaw._value || itemRaw;
      var nid = (n.noteCard && n.noteCard.noteId) || n.id || '';
      var xtoken = (n.noteCard && n.noteCard.xsecToken) || n.xsecToken || '';
      if (nid && !seen[nid]) {
        seen[nid] = true;
        result.push({
          id: nid,
          title: (n.noteCard && n.noteCard.displayTitle) || n.displayTitle || n.title || '',
          xsecToken: xtoken
        });
      }
    }
  }
  return JSON.stringify(result);
})()"""
    raw = bsk_eval(session, js, timeout=20)
    try:
        notes = json.loads(raw)
    except json.JSONDecodeError:
        print(f"❌ 笔记列表解析失败")
        print(f"   原始输出前 200 字符: {raw[:200]}")
        sys.exit(1)

    if not notes:
        print("❌ 未获取到笔记列表（可能是 XHS 页面结构变化）")
        sys.exit(1)

    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2))
    print(f"   ✅ {len(notes)} 条笔记 → {NOTES_FILE}")


# ═══ Step: extract ══════════════════════════════════════════

def cmd_extract(session=None, full=False):
    """用 curl + 完整 cookie 批量提取笔记详情。快、不触发风控。"""
    notes = load_notes_list()
    cookie = load_cookie()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    total = len(notes)
    ok = fail = skip = 0

    print(f"📝 提取 {total} 条笔记详情 (curl)...")
    print(f"📁 输出: {DATA_DIR}\n")

    for i, note in enumerate(notes):
        note_id = note["id"]
        token = note.get("xsecToken", "")
        sf = safe_filename(note.get("title", ""), note_id, i + 1)
        outfile = DATA_DIR / f"{sf}.json"

        if outfile.exists() and outfile.stat().st_size > 100:
            skip += 1
            continue

        url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}&xsec_source=pc_feed"
        html, status = curl_fetch(url, cookie=cookie, timeout=20)

        if status != 200 or not html or len(html) < 2000:
            fail += 1
            print(f"[{i+1}/{total}] ❌ {sf[:50]} ... HTTP {status}, {len(html or '')} bytes")
            continue

        # Extract __INITIAL_STATE__ from HTML (XHS may omit trailing semicolon)
        match = re.search(r'__INITIAL_STATE__=({.*?})</script>', html, re.DOTALL)
        if not match:
            match = re.search(r'__INITIAL_STATE__=({.*?});', html, re.DOTALL)
        if not match:
            fail += 1
            print(f"[{i+1}/{total}] ❌ {sf[:50]} ... __INITIAL_STATE__ not found")
            continue

        json_str = match.group(1).replace(':undefined', ':null')
        data = parse_note_state(json_str)

        if not data:
            fail += 1
            print(f"[{i+1}/{total}] ❌ {sf[:50]} ... parse failed")
            continue

        outfile.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        imgs = len(data.get("images", []))
        likes = data.get("interactInfo", {}).get("likeCount", "0")
        ok += 1
        print(f"[{i+1}/{total}] ✅ {sf[:50]} ... {imgs} imgs ❤️{likes}")

        time.sleep(0.3)

    print(f"\n✅ {ok} | ⏭️ {skip} | ❌ {fail}")
    _build_summary()


# ═══ Step: images ═══════════════════════════════════════════

def cmd_images():
    """下载所有原图。"""
    if not DATA_DIR.exists():
        print("❌ data/ 目录不存在，先运行 extract")
        sys.exit(1)
    data_files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and not f.startswith("_")]
    )
    if not data_files:
        print("❌ data/ 中没有笔记 JSON，先运行 extract")
        sys.exit(1)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    total = ok = fail = skip = 0

    print(f"📥 下载 {len(data_files)} 篇笔记的图片...\n")

    for df in data_files:
        note = json.loads((DATA_DIR / df).read_text())
        images = note.get("images", [])
        if not images:
            continue

        stem = Path(df).stem
        note_dir = IMAGES_DIR / stem
        note_dir.mkdir(exist_ok=True)

        title = note.get("title", "?")[:25]
        print(f"  📷 {title}... ({len(images)} imgs)", end=" ", flush=True)
        note_ok = 0

        for j, img in enumerate(images):
            url = img.get("url", "")
            if not url:
                continue
            if not url.startswith("http"):
                url = "http:" + url if url.startswith("//") else "http://" + url

            ext = ".webp"
            if ".png" in url.lower():
                ext = ".png"
            elif ".jpg" in url.lower() or ".jpeg" in url.lower():
                ext = ".jpg"

            filepath = note_dir / f"{j+1:02d}{ext}"

            if filepath.exists() and filepath.stat().st_size > 1000:
                skip += 1
                note_ok += 1
                continue

            # Try original quality first (strip !processing suffix)
            clean_url = url.split("!")[0] if "!" in url else url
            success = curl_download(clean_url, filepath)
            if not success:
                success = curl_download(url, filepath)

            if success:
                total += 1
                ok += 1
                note_ok += 1
            else:
                fail += 1
                print(f"❌{j+1}", end="", flush=True)

        print(f"✅ {note_ok}/{len(images)}")

    print(f"\n📊 下载: {ok} | 跳过: {skip} | 失败: {fail}")
    print(f"📁 {IMAGES_DIR}")


# ═══ Step: comments ═════════════════════════════════════════

def cmd_comments(session=None, full=False):
    """用 bsk navigate 逐条提取评论（XHS API 已封闭）。"""
    if not session:
        print("❌ comments 需要 bsk session")
        sys.exit(1)

    config = load_config()
    author_user_id = config.get("authorUserId", "")

    data_files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and not f.startswith("_")]
    )
    to_process = []
    for f in data_files:
        d = json.loads((DATA_DIR / f).read_text())
        cc = int(d.get("interactInfo", {}).get("commentCount", 0))
        if cc > 0 and not d.get("comments"):
            to_process.append((f, d["noteId"]))

    notes_list = json.loads(NOTES_FILE.read_text()) if NOTES_FILE.exists() else []
    token_map = {n["id"]: n.get("xsecToken", "") for n in notes_list}

    mode = "全部" if full else "仅作者"
    print(f"💬 抓取评论 — 模式: {mode} ({len(to_process)} 条笔记)\n")

    ok = 0
    for i, (fn, nid) in enumerate(to_process):
        token = token_map.get(nid, "")
        print(f"[{i+1}/{len(to_process)}] {fn[:40]}...", end=" ", flush=True)
        if not token:
            print("❌ no token"); continue

        # Navigate + retry if comments don't load
        for retry in range(3):
            bsk_eval(session, f"location.href='https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_feed'")
            time.sleep(8)
            # Check if noteDetailMap has comments
            check = bsk_eval(session, """
(function(){var ndm=window.__INITIAL_STATE__.note.noteDetailMap;var e=ndm[Object.keys(ndm)[0]];var cr=(e.comments._rawValue||e.comments._value||e.comments);return JSON.stringify({loaded:(cr.list||[]).length,total:cr.totalCount});})()
""", timeout=10)
            if check and '"loaded":0' not in check and '"loaded":' in check:
                break
            print(f"    重试 {retry+1}/3...")
        # Scroll comment container to load more parent comments
        for _ in range(15):
            bsk_eval(session, "var el=document.querySelector('.note-scroller');if(el)el.scrollTop=el.scrollHeight;", timeout=5)
            time.sleep(1.5)
        # Click all "展开 X 条回复" buttons to expand collapsed sub-comments
        for _ in range(15):
            cnt = bsk_eval(session, """(function(){
  var btns = document.querySelectorAll('.show-more');
  btns.forEach(function(b){ b.click(); });
  return btns.length;
})()""", timeout=5)
            if cnt == "0":
                break
            time.sleep(1)

        # Extract comments from noteDetailMap
        js = """(function(){
  var m = window.__INITIAL_STATE__.note.noteDetailMap._rawValue || window.__INITIAL_STATE__.note.noteDetailMap._value || window.__INITIAL_STATE__.note.noteDetailMap;
  for (var k in m) {
    var e = m[k];
    var d = e._rawValue || e._value || e;
    var cr = (d.comments && (d.comments._rawValue || d.comments._value || d.comments)) || {};
    var list = cr.list || [];
    if (!list.length) return '[]';
    var result = list.map(function(c){
      var cc = c._rawValue || c._value || c;
      var subs = (cc.subComments||[]).map(function(s){
        var ss = s._rawValue || s._value || s;
        return { id:ss.id, content:ss.content, likeCount:ss.likeCount, createTime:ss.createTime, ipLocation:ss.ipLocation,
          userInfo:{ userId:(ss.userInfo||{}).userId||'', nickname:(ss.userInfo||{}).nickname||'', image:(ss.userInfo||{}).image||'' } };
      });
      return { id:cc.id, content:cc.content, likeCount:cc.likeCount, createTime:cc.createTime, ipLocation:cc.ipLocation,
        userInfo:{ userId:(cc.userInfo||{}).userId||'', nickname:(cc.userInfo||{}).nickname||'', image:(cc.userInfo||{}).image||'' },
        subComments:subs, subCommentCount:cc.subCommentCount };
    });
    return JSON.stringify({totalCount: cr.totalCount, comments: result});
  }
  return '[]';
})()"""
        raw = bsk_eval(session, js, timeout=15)
        if not raw or raw == '[]':
            print("⚠️ 0"); continue

        raw = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', raw)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            print("❌ json"); continue

        all_comments = result.get("comments", [])

        # Filter: --full keeps all, default only keeps author's content
        if full or not author_user_id:
            saved = all_comments
            mode_label = "--full"
        else:
            saved = []
            for c in all_comments:
                is_author_toplevel = c["userInfo"]["userId"] == author_user_id
                author_subs = [s for s in c.get("subComments", []) if s["userInfo"]["userId"] == author_user_id]
                if is_author_toplevel and not author_subs:
                    saved.append(c)
                elif author_subs:
                    saved.append({
                        "id": c["id"],
                        "content": c["content"],
                        "userInfo": {"userId": "", "nickname": "", "image": ""},
                        "subComments": author_subs,
                    })
            mode_label = "仅作者"

        if not saved:
            print("⏭️  跳过")
            continue

        filepath = DATA_DIR / fn
        d = json.loads(filepath.read_text())
        d["comments"] = saved
        filepath.write_text(json.dumps(d, ensure_ascii=False, indent=2))

        sub_count = sum(len(c.get("subComments", [])) for c in saved)
        print(f"✅ {len(saved)} cmts + {sub_count} replies ({mode_label})")
        ok += 1
        time.sleep(0.5)

    print(f"\n✅ {ok}/{len(to_process)} 已更新")


# ═══ Step: watermark ════════════════════════════════════════

def cmd_watermark(text=None, force=False):
    """对 images/ 中的所有图片添加水印，输出到 images_wm/。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("❌ 需要 Pillow: pip install Pillow")
        sys.exit(1)

    config = load_config()
    if not text:
        text = config.get("watermarkText") or config.get("authorName") or config.get("authorRedId") or "笔记"

    IMAGES_WM_DIR.mkdir(parents=True, exist_ok=True)
    img_dirs = sorted(d for d in IMAGES_DIR.iterdir() if d.is_dir())
    total = done = 0

    for note_dir in img_dirs:
        wm_dir = IMAGES_WM_DIR / note_dir.name
        wm_dir.mkdir(exist_ok=True)

        for img_file in sorted(note_dir.iterdir()):
            if img_file.suffix.lower() not in ('.webp', '.jpg', '.jpeg', '.png'):
                continue
            total += 1
            out_file = wm_dir / img_file.name

            if not force and out_file.exists() and out_file.stat().st_size > 100:
                done += 1
                continue

            try:
                img = Image.open(img_file).convert("RGBA")
                w, h = img.size

                # Watermark layer
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)

                # Font size proportional to image width
                font_size = max(12, int(w * 0.03))
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", font_size)
                except Exception:
                    font = ImageFont.load_default()

                # Position: bottom-right corner
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                pos = (w - tw - 20, h - th - 20)

                # Semi-transparent white text with shadow
                draw.text((pos[0] + 1, pos[1] + 1), text, font=font, fill=(0, 0, 0, 80))
                draw.text(pos, text, font=font, fill=(255, 255, 255, 100))

                result = Image.alpha_composite(img, overlay)
                if out_file.suffix.lower() == '.webp':
                    result.convert("RGB").save(out_file, "WEBP", quality=80)
                elif out_file.suffix.lower() in ('.jpg', '.jpeg'):
                    result.convert("RGB").save(out_file, "JPEG", quality=80)
                else:
                    result.save(out_file)

                done += 1
            except Exception as e:
                print(f"  ⚠️ {img_file.name}: {e}")

    print(f"🖼️  水印: {done}/{total} 张图片 → {IMAGES_WM_DIR}")


# ═══ Step: translate ════════════════════════════════════════

def cmd_translate():
    """调用 translate_data.py 翻译中文内容。"""
    script = Path(__file__).parent / "translate_data.py"
    if not script.exists():
        print(f"❌ 翻译脚本不存在: {script}")
        sys.exit(1)

    print("🌐 调用 AI 翻译...")
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        print("⚠️ 翻译失败，可稍后重试: python3 xhs_collect.py translate")


# ═══ Step: build ════════════════════════════════════════════

def _image_dir_for(note_id, title):
    """Find the image directory name matching a note's data file stem."""
    # The data file stem looks like: 001_忆江南 _6a5514b40000000011017ad2
    # The image dir has the same name (with the space before noteId)
    for d in sorted(IMAGES_DIR.iterdir()):
        if d.is_dir() and d.name.endswith(note_id):
            return d.name
    return None

def _build_summary():
    """Generate _summary.json from data/ JSONs."""
    summary = {"notes": []}
    for f in sorted(DATA_DIR.iterdir()):
        if f.name.startswith("_") or not f.name.endswith(".json"):
            continue
        try:
            note = json.loads(f.read_text())
            summary["notes"].append({
                "noteId": note["noteId"],
                "title": note.get("title", ""),
                "images": len(note.get("images", [])),
                "likeCount": note.get("interactInfo", {}).get("likeCount", "0"),
                "collectCount": note.get("interactInfo", {}).get("collectCount", "0"),
                "commentCount": note.get("interactInfo", {}).get("commentCount", "0"),
                "file": f.name,
            })
        except Exception:
            pass
    (DATA_DIR / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

def cmd_build():
    """从 data/*.json 重新生成 data.js 和 manifest.json。"""
    js_file = BACKUP_DIR / "data.js"
    manifest_file = BACKUP_DIR / "manifest.json"

    # Read old data.js to preserve translations
    old_translations = {}
    if js_file.exists():
        try:
            raw = js_file.read_text()
            old_notes = json.loads(raw.split('= ', 1)[1].rstrip(';'))
            for n in old_notes:
                nid = n.get("noteId", "")
                for key in ("_titleEn", "_descEn"):
                    if n.get(key):
                        old_translations.setdefault(nid, {})[key] = n[key]
                for ci, c in enumerate(n.get("comments", [])):
                    for key in ("_contentEn",):
                        if c.get(key):
                            old_translations.setdefault(nid, {}).setdefault("comments", {})[c.get("id", str(ci))] = c[key]
                    for si, s in enumerate(c.get("subComments", [])):
                        for key in ("_contentEn",):
                            if s.get(key):
                                old_translations.setdefault(nid, {}).setdefault("subComments", {})[s.get("id", str(si))] = s[key]
                    if c.get("userInfo", {}).get("_nicknameEn"):
                        old_translations.setdefault(nid, {}).setdefault("commentUsers", {})[c["userInfo"].get("userId", ci)] = c["userInfo"]["_nicknameEn"]
        except Exception:
            old_translations = {}

    # Build notes
    notes = []
    data_files = sorted(
        [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and not f.startswith("_")]
    )
    for f in data_files:
        note = json.loads((DATA_DIR / f).read_text())
        nid = note["noteId"]

        # Restore translations
        saved = old_translations.get(nid, {})
        for key in ("_titleEn", "_descEn"):
            if key in saved:
                note[key] = saved[key]
        for ci, c in enumerate(note.get("comments", [])):
            saved_cmts = saved.get("comments", {})
            cid = c.get("id", str(ci))
            if cid in saved_cmts:
                c["_contentEn"] = saved_cmts[cid]
            saved_users = saved.get("commentUsers", {})
            uid = c.get("userInfo", {}).get("userId", ci)
            if uid in saved_users:
                c["userInfo"]["_nicknameEn"] = saved_users[uid]
            for si, s in enumerate(c.get("subComments", [])):
                saved_subs = saved.get("subComments", {})
                sid = s.get("id", str(si))
                if sid in saved_subs:
                    s["_contentEn"] = saved_subs[sid]

        # Image paths
        stem = Path(f).stem
        img_dir = _image_dir_for(nid, note.get("title", "")) or stem
        # Strip original CDN URLs — not needed for local display
        for img in note.get("images", []):
            img.pop("url", None)
            img.pop("urlPre", None)
            img.pop("urlDefault", None)
        note["_file"] = f
        note["_imgDir"] = img_dir
        # Cover image — pick the FIRST image (sorted by filename)
        cover = next((img for img in sorted(os.listdir(IMAGES_WM_DIR / img_dir))
                     if not img.startswith('.')) if (IMAGES_WM_DIR / img_dir).exists() else None, None)
        if not cover:
            cover = next((img for img in sorted(os.listdir(IMAGES_DIR / img_dir))
                         if not img.startswith('.')) if (IMAGES_DIR / img_dir).exists() else None, None)
        note["_coverPath"] = f"images_wm/{img_dir}/{cover}" if cover else ""
        # Sticky first 2
        note["_sticky"] = len(notes) < 2 if note.get("_sticky") is None else note.get("_sticky", False)

        notes.append(note)

    # Write data.js
    js = "window.__XHS_NOTES__ = " + json.dumps(notes, ensure_ascii=False) + ";"
    js_file.write_text(js)
    print(f"📦 data.js: {len(notes)} notes ({js_file.stat().st_size:,} bytes)")

    # Write config.js (generated from config.json for web use)
    cfg = load_config()
    if cfg:
        cfg_js = "window.__XHS_CONFIG__ = " + json.dumps(cfg, ensure_ascii=False) + ";"
        (BACKUP_DIR / "config.js").write_text(cfg_js)

    # Write manifest.json
    manifest = []
    for n in notes:
        manifest.append({
            "file": n["_file"],
            "noteId": n["noteId"],
            "title": n.get("title", ""),
            "likeCount": n.get("interactInfo", {}).get("likeCount", "0"),
            "collectCount": n.get("interactInfo", {}).get("collectCount", "0"),
            "imageCount": len(n.get("images", [])),
            "cover": n.get("_coverPath", ""),
            "tags": n.get("tags", []),
        })
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False))
    print(f"📋 manifest.json: {len(manifest)} entries")

    # Copy admin.html template (first time only)
    admin_file = BACKUP_DIR / "admin.html"
    if not admin_file.exists():
        print("⚠️ admin.html 不存在，请手动创建或从模板复制")


# ═══ Step: serve ════════════════════════════════════════════

def cmd_serve():
    """启动本地预览。"""
    import http.server
    import socketserver

    port = 8088
    os.chdir(str(BACKUP_DIR))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"🚀 本地预览: http://localhost:{port}")
        print(f"   管理配置: http://localhost:{port}/admin.html")
        print(f"   Ctrl+C 停止")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 已停止")


# ═══ Combo steps ════════════════════════════════════════════

def cmd_update(session):
    """增量更新：extract(含评论) + images + build。"""
    print("🔄 增量更新...\n")
    cmd_extract(session)
    print()
    cmd_images()
    print()
    cmd_build()

def cmd_run_all(session):
    """完整流程：从零到部署。"""
    steps = [
        ("auth", lambda: cmd_auth(session)),
        ("list", lambda: cmd_list(session)),
        ("extract(含评论)", lambda: cmd_extract(session)),
        ("images", cmd_images),
        ("build", cmd_build),
    ]
    print("🚀 完整流程\n")
    for name, fn in steps:
        print(f"\n{'─' * 50}")
        print(f"  📌 {name}")
        print(f"{'─' * 50}")
        fn()
    print(f"\n{'=' * 50}")
    print("✅ 全部完成！运行 serve 启动预览:")
    print("   python3 xhs_collect.py serve")


# ═══ CLI ════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="小红书数据采集 & 本地备份 — 一站式脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            示例:
              python3 xhs_collect.py auth my-session
              python3 xhs_collect.py list my-session
              python3 xhs_collect.py extract
              python3 xhs_collect.py images
              python3 xhs_collect.py comments my-session           # 只抓作者评论
              python3 xhs_collect.py comments my-session --full    # 抓全部评论
              python3 xhs_collect.py update my-session             # 增量更新
              python3 xhs_collect.py run-all my-session            # 从零完整流程
        """),
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    p_auth = sub.add_parser("auth", help="浏览器登录态提取")
    p_auth.add_argument("session", help="bsk session ID")

    p_list = sub.add_parser("list", help="抓取笔记列表")
    p_list.add_argument("session", help="bsk session ID")

    sub.add_parser("extract", help="用 curl 批量提取笔记详情（需先 auth 粘贴完整 cookie）")

    sub.add_parser("images", help="下载所有原图")

    p_cmts = sub.add_parser("comments", help="用 bsk 抓取评论")
    p_cmts.add_argument("session", help="bsk session ID")
    p_cmts.add_argument("--full", action="store_true", help="保留全部评论（含他人）")

    p_wm = sub.add_parser("watermark", help="批量添加水印")
    p_wm.add_argument("--text", help="水印文字（默认从 config.json 读取）")
    p_wm.add_argument("--force", action="store_true", help="强制重新生成所有水印（默认跳过已存在的）")

    sub.add_parser("translate", help="AI 翻译中文→英文")
    sub.add_parser("build", help="重新生成 data.js + manifest.json")
    sub.add_parser("serve", help="启动本地预览 (8088)")

    p_up = sub.add_parser("update", help="增量更新")
    p_up.add_argument("session", help="bsk session ID")

    p_all = sub.add_parser("run-all", help="完整流程")
    p_all.add_argument("session", help="bsk session ID")

    args = parser.parse_args()

    if args.command == "auth":
        cmd_auth(args.session)
    elif args.command == "list":
        cmd_list(args.session)
    elif args.command == "extract":
        cmd_extract()
    elif args.command == "images":
        cmd_images()
    elif args.command == "comments":
        cmd_comments(args.session, full=args.full)
    elif args.command == "watermark":
        cmd_watermark(text=args.text, force=args.force)
    elif args.command == "translate":
        cmd_translate()
    elif args.command == "build":
        cmd_build()
    elif args.command == "serve":
        cmd_serve()
    elif args.command == "update":
        cmd_update(args.session)
    elif args.command == "run-all":
        cmd_run_all(args.session)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

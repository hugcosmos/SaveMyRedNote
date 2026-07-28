#!/usr/bin/env python3
"""
Translate Chinese content in XHS backup data to English using Agnes AI.
Set AGNES_API_KEY in your environment, then run: python3 translate_data.py

Reads data.js, finds all Chinese text in:
  - Post titles & descriptions
  - Comment content
  - Usernames
And translates them via the Agnes AI API.

Output: data.js with _titleEn, _descEn, _contentEn, _nicknameEn fields added.
"""

import json
import os
import re
import ssl
import sys
import time
from urllib.request import Request, urlopen, ProxyHandler, build_opener, install_opener
from urllib.error import URLError

API_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
MODEL = "agnes-2.0-flash"
BATCH_SIZE = 10
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")

API_KEY = os.environ.get("AGNES_API_KEY", "")

if not API_KEY:
    print("❌ AGNES_API_KEY not set. Run: export AGNES_API_KEY=sk-your-key")
    sys.exit(1)

# Setup proxy & SSL
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

from urllib.request import HTTPSHandler
proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
if proxy:
    ph = ProxyHandler({"https": proxy, "http": proxy})
    install_opener(build_opener(ph, HTTPSHandler(context=ctx)))
    print(f"🔗 Using proxy: {proxy}")
else:
    install_opener(build_opener(HTTPSHandler(context=ctx)))


def strip_hashtags(text):
    """Remove hashtags from text entirely (not re-appended)."""
    tags = re.findall(r'#\S+', text)
    for tag in tags:
        text = text.replace(tag, '')
    return re.sub(r'\n\s*\n\s*$', '', text).rstrip()

import string

def make_id(idx):
    """Short alphanumeric IDs: a, b, ..., z, aa, ab, ..."""
    letters = string.ascii_lowercase
    if idx < 26:
        return letters[idx]
    return letters[idx // 26 - 1] + letters[idx % 26]

def has_chinese(s):
    return bool(re.search(r'[一-鿿]', s or ''))


def call_llm(texts):
    """Translate a batch of texts via Agnes AI. Returns dict {id: translation}."""
    # Build ID-to-text mapping, skipping empty texts
    id_map = {}
    for i, t in enumerate(texts):
        if t and t.strip():
            id_map[make_id(i)] = t
    if not id_map:
        return {}

    prompt = (
        "Translate each Chinese text to natural, fluent English. "
        "Keep non-Chinese text unchanged. Do not add explanations.\n\n"
        + "\n".join(f"[{id_}] {t[:800]}" for id_, t in id_map.items())
        + "\n\nReturn ONLY a JSON object mapping each ID to its translation: "
        + '{"a": "translation1", "b": "translation2", ...}'
        + "\nDo NOT return an array. Use the exact same IDs I gave you."
    )

    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a translator. Return only a JSON object mapping text IDs to translations, nothing else."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }).encode()

    req = Request(API_URL, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })

    try:
        resp = urlopen(req, timeout=60)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]

        # Extract JSON object — handle both bare and code-fenced forms
        content_clean = re.sub(r'```(?:json)?\s*', '', content).strip()

        # Try parsing JSON object with multiple recovery strategies
        obj = None
        match = re.search(r'\{.*\}', content_clean, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group())
            except json.JSONDecodeError:
                # Try fixing common LLM JSON mistakes:
                # 1. Unquoted keys: {a: "x"} → {"a": "x"}
                raw = match.group()
                raw_fixed = re.sub(r'(?<=\{|\s|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', raw)
                # 2. Unquoted string values: {"a": value with spaces} → needs different handling, skip
                # 3. Trailing commas: {"a": "x",} → {"a": "x"}
                raw_fixed = re.sub(r',\s*}', '}', raw_fixed)
                raw_fixed = re.sub(r',\s*\]', ']', raw_fixed)
                try:
                    obj = json.loads(raw_fixed)
                except json.JSONDecodeError:
                    pass

                # If still failing, try extracting key-value pairs with regex
                if obj is None:
                    fallback = {}
                    pairs = re.findall(r'"([a-z]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_fixed)
                    for k, v in pairs:
                        if k in id_map:
                            fallback[k] = v
                    if fallback:
                        obj = fallback

        if obj and isinstance(obj, dict):
            return {str(k): str(v) for k, v in obj.items()}

        # Fallback: LLM returned an array instead of object
        match_arr = re.search(r'\[.*\]', content_clean, re.DOTALL)
        if match_arr:
            try:
                arr = json.loads(match_arr.group())
            except json.JSONDecodeError:
                arr = []
            if arr:
                print(f"  ⚠️ LLM returned array, using positional fallback")
                keys = list(id_map.keys())
                return {keys[j]: str(arr[j]) for j in range(min(len(keys), len(arr)))}

        print(f"  ⚠️ Parse failed: {content[:200]}")
        return {}
    except URLError as e:
        print(f"  ❌ API error: {e}")
        return {}
    except Exception as e:
        print(f"  ❌ {e}")
        return {}


def main():
    # Load data
    with open(DATA_FILE, 'r') as f:
        raw = f.read()
    prefix = raw.split('= ', 1)[0] + '= '
    notes = json.loads(raw.split('= ', 1)[1].rstrip(';'))
    print(f"📦 {len(notes)} notes\n")

    # Collect unique Chinese texts
    to_translate = []
    for n in notes:
        if has_chinese(n.get('title', '')):
            to_translate.append(('title', n))
        if has_chinese(n.get('description', '')):
            to_translate.append(('desc', n))
        for c in n.get('comments', []):
            if has_chinese(c.get('content', '')):
                to_translate.append(('comment', c))
            if has_chinese(c.get('userInfo', {}).get('nickname', '')):
                to_translate.append(('nickname', c['userInfo']))
            for s in (c.get('subComments') or []):
                if has_chinese(s.get('content', '')):
                    to_translate.append(('subcomment', s))
                if has_chinese(s.get('userInfo', {}).get('nickname', '')):
                    to_translate.append(('subnickname', s['userInfo']))

    seen, unique = set(), []
    for typ, obj in to_translate:
        if typ == 'title': text = obj.get('title', '')
        elif typ == 'desc': text = obj.get('description', '')
        elif typ in ('comment','subcomment'): text = obj.get('content', '')
        elif typ in ('nickname','subnickname'): text = obj.get('nickname', '')
        else: text = ''
        if not text.strip(): continue
        if text in seen: continue
        seen.add(text)
        # Strip hashtags before sending to API
        clean_text = strip_hashtags(text)
        unique.append((typ, obj, clean_text, text))

    print(f"📝 {len(unique)} unique texts to translate\n")

    # Batch translate
    translations = {}
    retry_queue = []  # items that failed in batch, to retry individually

    for i in range(0, len(unique), BATCH_SIZE):
        batch = unique[i:i + BATCH_SIZE]
        texts = [t[2] for t in batch]  # clean_text for API
        n = i // BATCH_SIZE + 1
        total = (len(unique) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[{n}/{total}] {len(batch)} items...", end=" ", flush=True)

        results = call_llm(texts)
        for j, (typ, obj, clean_text, key) in enumerate(batch):
            id_ = make_id(j)
            if id_ in results:
                translations[f"{typ}:{key}"] = results[id_]
            elif clean_text and clean_text.strip():
                retry_queue.append((typ, obj, clean_text, key))
        print(f"✅ {len(results)}/{len(batch)}")
        time.sleep(0.5)

    # Retry failed items individually
    if retry_queue:
        print(f"\n🔄 Retrying {len(retry_queue)} failed items individually...")
        for idx, (typ, obj, clean_text, key) in enumerate(retry_queue):
            print(f"  [{idx+1}/{len(retry_queue)}] {clean_text[:60]}...", end=" ", flush=True)
            results = call_llm([clean_text])  # single item batch
            if results and 'a' in results:
                translations[f"{typ}:{key}"] = results['a']
                print("✅")
            else:
                print("❌")
            time.sleep(0.3)

    # Apply
    for n in notes:
        k = f"title:{n.get('title', '')}"
        if k in translations: n['_titleEn'] = translations[k]
        k = f"desc:{n.get('description', '')}"
        if k in translations: n['_descEn'] = translations[k]
        for c in n.get('comments', []):
            k = f"comment:{c.get('content', '')}"
            if k in translations: c['_contentEn'] = translations[k]
            k = f"nickname:{c.get('userInfo', {}).get('nickname', '')}"
            if k in translations: c['userInfo']['_nicknameEn'] = translations[k]
            for s in (c.get('subComments') or []):
                k = f"subcomment:{s.get('content', '')}"
                if k in translations: s['_contentEn'] = translations[k]
                k = f"subnickname:{s.get('userInfo', {}).get('nickname', '')}"
                if k in translations: s['userInfo']['_nicknameEn'] = translations[k]

    js = prefix + json.dumps(notes, ensure_ascii=False) + ';'
    with open(DATA_FILE, 'w') as f:
        f.write(js)
    print(f"\n✅ Saved to {DATA_FILE}")


if __name__ == "__main__":
    main()

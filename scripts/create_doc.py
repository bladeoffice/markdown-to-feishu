"""
feishu_create_doc - Create Feishu documents from Markdown files.
"""

import warnings
warnings.filterwarnings("ignore", category=Warning)

import sys
import re
import os
import time
import requests
from pathlib import Path
import winreg

# ── Config ──────────────────────────────────────────────────────────────────

def _get_registry_env(var, scope="Machine"):
    try:
        root = winreg.HKEY_LOCAL_MACHINE if scope == "Machine" else winreg.HKEY_CURRENT_USER
        key = winreg.OpenKey(root, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, var)
            return val
        finally:
            winreg.CloseKey(key)
    except WindowsError:
        return None

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID") or _get_registry_env("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET") or _get_registry_env("FEISHU_APP_SECRET")

if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
    raise RuntimeError("FEISHU credentials not found.")

API_BASE = r"https://open.feishu.cn/open-apis"
DEFAULT_FOLDER = ""

# ── Auth & Doc Creation ─────────────────────────────────────────────────────

def get_token():
    resp = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0: raise Exception(f"Auth failed: {data.get('msg')}")
    return data["tenant_access_token"]

def create_document(token, title, folder_token=None):
    payload = {"title": title}
    if folder_token: payload["folder_token"] = folder_token
    resp = requests.post(
        f"{API_BASE}/docx/v1/documents",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0: raise Exception(f"Create doc failed: {data.get('msg')}")
    return data["data"]["document"]["document_id"]

# ── Media & Image Update ───────────────────────────────────────────────────

def upload_media(token, image_path, parent_node):
    file_size = os.path.getsize(image_path)
    file_name = os.path.basename(image_path)
    with open(image_path, "rb") as f:
        resp = requests.post(
            f"{API_BASE}/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data={"parent_type": "docx_image", "parent_node": parent_node,
                  "file_name": file_name, "size": str(file_size)},
            files={"file": (file_name, f)}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0: raise Exception(f"Upload media failed: {data.get('msg')}")
    return data["data"]["file_token"]

def batch_update_image_blocks(token, doc_id, image_updates):
    if not image_updates: return
    req_data = [{"block_id": bid, "replace_image": {"token": ft}} for bid, ft in image_updates]
    resp = requests.patch(
        f"{API_BASE}/docx/v1/documents/{doc_id}/blocks/batch_update",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"requests": req_data}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0: raise Exception(f"Batch update failed: {data.get('msg')}")

# ── Convert ─────────────────────────────────────────────────────────────────

def convert_md_to_blocks(token, doc_id, md_content):
    resp = requests.post(
        f"{API_BASE}/docx/v1/documents/blocks/convert",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        json={"content": md_content, "doc_id": doc_id, "content_type": "markdown"}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0: raise Exception(f"Convert failed: {data.get('msg')}")
    result = data.get("data", {})
    return result.get("blocks", []), result.get("first_level_block_ids", [])

# ── Insert blocks ───────────────────────────────────────────────────────────

def _strip_meta(block):
    block.pop("block_id", None)
    block.pop("parent_id", None)
    block.pop("revision_id", None)
    if block.get("table"): block["table"].pop("merge_info", None)
    return block

def insert_blocks(token, doc_id, parent_block_id, raw_blocks, first_level_ids):
    if not raw_blocks: return []
    id_map = {b["block_id"]: b for b in raw_blocks}
    # 核心：严格按 first_level_block_ids 的正确顺序重排
    ordered_blocks = [id_map[bid] for bid in first_level_ids if bid in id_map]

    inserted_ids = []
    for i in range(0, len(ordered_blocks), 50):
        batch = ordered_blocks[i:i + 50]
        clean_batch = [_strip_meta(b.copy()) for b in batch]
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{API_BASE}/docx/v1/documents/{doc_id}/blocks/{parent_block_id}/children",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                    json={"children": clean_batch}, timeout=30)
                data = resp.json()
                if resp.status_code == 429 or data.get("code") == 99991400:
                    time.sleep(1.5 ** attempt + 0.5)
                    continue
                resp.raise_for_status()
                if data.get("code") != 0:
                    raise Exception(f"Insert failed: {data.get('msg')}")
                def extract_ids(children):
                    ids = []
                    for c in children:
                        if c.get("block_id"): ids.append(c["block_id"])
                        if c.get("children"): ids.extend(extract_ids(c["children"]))
                    return ids
                inserted_ids.extend(extract_ids(data.get("data", {}).get("children", [])))
                break
            except requests.exceptions.HTTPError as e:
                if attempt == 2: raise
                time.sleep(1.5 ** attempt + 0.5)
        time.sleep(0.3)
    return inserted_ids

# ── Helpers ─────────────────────────────────────────────────────────────────

def extract_local_image_paths(md_text, md_dir):
    paths = []
    for m in re.finditer(r'!\[.*?\]\((.*?)\)', md_text):
        p = m.group(1).strip()
        if not p.startswith(('http://', 'https://')):
            paths.append(os.path.join(md_dir, p))
    return paths

def extract_title(md_text, fallback_name):
    fm = re.match(r'^---\n(.*?)\n---', md_text, re.DOTALL)
    clean_md = re.sub(r'^---\n.*?\n---\n?', '', md_text, count=1, flags=re.DOTALL).lstrip()
    clean_md = re.sub(r'^\s*---\s*\n?', '', clean_md).lstrip()
    title = None
    if fm:
        m = re.search(r'^title:\s*([^\n]+)', fm.group(1), re.MULTILINE)
        if m: title = m.group(1).strip().strip('"\'')
    if not title:
        h1 = re.search(r'^#\s+(.+)$', clean_md, re.MULTILINE)
        if h1: title = h1.group(1).strip()
    if not title: title = fallback_name
    return title, clean_md

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    md_path = sys.argv[1]
    folder_token = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_FOLDER
    custom_title = sys.argv[3] if len(sys.argv) > 3 else None

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    md_dir = os.path.dirname(os.path.abspath(md_path))
    title, clean_md = extract_title(md_text, Path(md_path).stem)
    if custom_title: title = custom_title

    print(f"📄 Creating: {title}")
    token = get_token()
    doc_id = create_document(token, title, folder_token)
    
    blocks, first_level_ids = convert_md_to_blocks(token, doc_id, clean_md)
    inserted_ids = insert_blocks(token, doc_id, doc_id, blocks, first_level_ids)
    
    # 精准匹配 Image 块的真实 ID
    id_map = {b["block_id"]: b for b in blocks}
    ordered_blocks = [id_map[bid] for bid in first_level_ids if bid in id_map]
    image_inserted_indices = [idx for idx, ob in enumerate(ordered_blocks) if ob.get("block_type") == 27]
    
    local_imgs = extract_local_image_paths(clean_md, md_dir)
    updates = []
    for img_idx, ins_pos in enumerate(image_inserted_indices):
        if ins_pos < len(inserted_ids) and img_idx < len(local_imgs):
            abs_path = local_imgs[img_idx]
            if os.path.exists(abs_path):
                real_block_id = inserted_ids[ins_pos]
                try:
                    ft = upload_media(token, abs_path, real_block_id)
                    updates.append((real_block_id, ft))
                except Exception as e:
                    print(f"   ⚠️ Img fail: {os.path.basename(abs_path)} - {e}")

    if updates:
        try:
            batch_update_image_blocks(token, doc_id, updates)
        except Exception as e:
            print(f"   ⚠️ Update fail: {e}")

    print(f"✅ Done: https://feishu.cn/docx/{doc_id}")

if __name__ == "__main__":
    main()

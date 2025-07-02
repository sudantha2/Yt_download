import os
import tempfile
import asyncio
import logging
import random
import time
import shutil
from urllib.parse import quote_plus
from typing import Dict, List, Optional

import aiohttp
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import subprocess

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
DOWNLOADS_DIR = "downloads"
RESULTS_PER_PAGE = 5

# User agents to rotate for avoiding detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# Store user search sessions
user_sessions: Dict[int, Dict] = {}

class YouTubeDownloader:
    def __init__(self):
        self.session = None
        
    async def create_session(self):
        """Create aiohttp session with random user agent"""
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        connector = aiohttp.TCPConnector(
            limit=10,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout
        )
    
    async def search_youtube(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search YouTube videos using yt-dlp"""
        if not self.session:
            await self.create_session()
            
        try:
            # Add random delay to avoid rate limiting
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch50:',  # Search for up to 50 results
                'http_headers': {
                    'User-Agent': random.choice(USER_AGENTS),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                },
                'extractor_retries': 3,
                'fragment_retries': 3,
                'skip_unavailable_fragments': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    search_results = await asyncio.get_event_loop().run_in_executor(
                        None, ydl.extract_info, f"ytsearch{max_results}:{query}", False
                    )
                    
                    if search_results and 'entries' in search_results:
                        results = []
                        for entry in search_results['entries']:
                            if entry:
                                results.append({
                                    'id': entry.get('id', ''),
                                    'title': entry.get('title', 'Unknown Title'),
                                    'duration': entry.get('duration', 0),
                                    'uploader': entry.get('uploader', 'Unknown'),
                                    'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                                })
                        return results
                    
                except Exception as e:
                    logger.error(f"Search error: {e}")
                    return []
                    
        except Exception as e:
            logger.error(f"Search session error: {e}")
            return []
        
        return []
    
    async def download_media(self, url: str, download_type: str, user_id: int) -> Optional[str]:
        """Download media from YouTube"""
        try:
            # Create user-specific download directory
            user_dir = os.path.join(DOWNLOADS_DIR, str(user_id))
            os.makedirs(user_dir, exist_ok=True)
            
            # Configure yt-dlp options based on download type
            if download_type == 'audio':
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(user_dir, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'http_headers': {
                        'User-Agent': random.choice(USER_AGENTS),
                    },
                    'extractor_retries': 3,
                    'fragment_retries': 3,
                    'skip_unavailable_fragments': True,
                    'ignoreerrors': True,
                }
            else:  # video
                ydl_opts = {
                    'format': 'best[height<=720]/best',
                    'outtmpl': os.path.join(user_dir, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    'http_headers': {
                        'User-Agent': random.choice(USER_AGENTS),
                    },
                    'extractor_retries': 3,
                    'fragment_retries': 3,
                    'skip_unavailable_fragments': True,
                    'ignoreerrors': True,
                }
            
            # Add random delay before download
            await asyncio.sleep(random.uniform(1, 3))
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get the filename
                info = await asyncio.get_event_loop().run_in_executor(
                    None, ydl.extract_info, url, False
                )
                
                if not info:
                    return None
                
                # Download the file
                await asyncio.get_event_loop().run_in_executor(
                    None, ydl.download, [url]
                )
                
                # Find the downloaded file
                title = info.get('title', 'Unknown')
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                
                # Look for the file with different extensions
                possible_extensions = ['mp3', 'mp4', 'webm', 'm4a', 'opus']
                for ext in possible_extensions:
                    filepath = os.path.join(user_dir, f"{safe_title}.{ext}")
                    if os.path.exists(filepath):
                        return filepath
                
                # If exact match not found, look for any file in the directory
                files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))]
                if files:
                    # Return the most recently created file
                    latest_file = max(files, key=lambda f: os.path.getctime(os.path.join(user_dir, f)))
                    return os.path.join(user_dir, latest_file)
                
                return None
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

# Initialize downloader
downloader = YouTubeDownloader()

def format_duration(seconds):
    """Format duration from seconds to MM:SS or HH:MM:SS"""
    if not seconds:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def create_search_keyboard(results: List[Dict], page: int, total_pages: int, user_id: int, search_type: str) -> InlineKeyboardMarkup:
    """Create inline keyboard for search results"""
    keyboard = []
    
    # Add result buttons (5 per page)
    start_idx = page * RESULTS_PER_PAGE
    end_idx = min(start_idx + RESULTS_PER_PAGE, len(results))
    
    for i in range(start_idx, end_idx):
        result = results[i]
        title = result['title'][:50] + "..." if len(result['title']) > 50 else result['title']
        duration = format_duration(result['duration'])
        
        button_text = f"🎵 {title} [{duration}]" if search_type == 'song' else f"🎬 {title} [{duration}]"
        callback_data = f"download_{search_type}_{i}_{user_id}"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page-1}_{user_id}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}_{user_id}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}")])
    
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_text = """
🎵 **YouTube Downloader Bot** 🎬

Welcome! I can help you download songs and videos from YouTube.

**Commands:**
• `/song <song name>` - Search and download audio (MP3)
• `/vid <video name>` - Search and download video (MP4)

**Example:**
• `/song Imagine Dragons Believer`
• `/vid Funny cat videos`

Just send a command and I'll show you search results with navigation buttons!
    """
    
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def song_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /song command"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a song name!\n\nExample: `/song Imagine Dragons Believer`", parse_mode=ParseMode.MARKDOWN)
        return
    
    query = " ".join(context.args)
    user_id = update.effective_user.id
    
    # Send searching message
    searching_msg = await update.message.reply_text("🔍 Searching for songs...")
    
    try:
        # Search for results
        results = await downloader.search_youtube(query, max_results=50)
        
        if not results:
            await searching_msg.edit_text("❌ No results found. Please try a different search term.")
            return
        
        # Store user session
        user_sessions[user_id] = {
            'results': results,
            'query': query,
            'type': 'song',
            'page': 0
        }
        
        # Calculate pagination
        total_pages = (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
        
        # Create keyboard
        keyboard = create_search_keyboard(results, 0, total_pages, user_id, 'song')
        
        # Update message with results
        text = f"🎵 **Search Results for:** `{query}`\n\n📊 Found {len(results)} songs\n\nSelect a song to download:"
        await searching_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Song search error: {e}")
        await searching_msg.edit_text("❌ An error occurred while searching. Please try again.")

async def vid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /vid command"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a video name!\n\nExample: `/vid Funny cat videos`", parse_mode=ParseMode.MARKDOWN)
        return
    
    query = " ".join(context.args)
    user_id = update.effective_user.id
    
    # Send searching message
    searching_msg = await update.message.reply_text("🔍 Searching for videos...")
    
    try:
        # Search for results
        results = await downloader.search_youtube(query, max_results=50)
        
        if not results:
            await searching_msg.edit_text("❌ No results found. Please try a different search term.")
            return
        
        # Store user session
        user_sessions[user_id] = {
            'results': results,
            'query': query,
            'type': 'vid',
            'page': 0
        }
        
        # Calculate pagination
        total_pages = (len(results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
        
        # Create keyboard
        keyboard = create_search_keyboard(results, 0, total_pages, user_id, 'vid')
        
        # Update message with results
        text = f"🎬 **Search Results for:** `{query}`\n\n📊 Found {len(results)} videos\n\nSelect a video to download:"
        await searching_msg.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Video search error: {e}")
        await searching_msg.edit_text("❌ An error occurred while searching. Please try again.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = update.effective_user.id
    
    # Handle page navigation
    if callback_data.startswith("page_"):
        parts = callback_data.split("_")
        page = int(parts[1])
        callback_user_id = int(parts[2])
        
        if user_id != callback_user_id:
            await query.answer("❌ This is not your search!", show_alert=True)
            return
        
        if user_id not in user_sessions:
            await query.edit_message_text("❌ Search session expired. Please start a new search.")
            return
        
        session = user_sessions[user_id]
        session['page'] = page
        
        # Update keyboard
        total_pages = (len(session['results']) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
        keyboard = create_search_keyboard(session['results'], page, total_pages, user_id, session['type'])
        
        # Update message
        emoji = "🎵" if session['type'] == 'song' else "🎬"
        text = f"{emoji} **Search Results for:** `{session['query']}`\n\n📊 Found {len(session['results'])} {'songs' if session['type'] == 'song' else 'videos'}\n\nSelect a {'song' if session['type'] == 'song' else 'video'} to download:"
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    
    # Handle cancel
    elif callback_data.startswith("cancel_"):
        callback_user_id = int(callback_data.split("_")[1])
        
        if user_id != callback_user_id:
            await query.answer("❌ This is not your search!", show_alert=True)
            return
        
        # Get user info
        user = update.effective_user
        user_link = f"[{user.first_name}](tg://user?id={user.id})"
        
        # Clean up session
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        await query.edit_message_text(
            f"❌ Search cancelled by {user_link}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Handle download
    elif callback_data.startswith("download_"):
        parts = callback_data.split("_")
        download_type = parts[1]  # 'song' or 'vid'
        result_index = int(parts[2])
        callback_user_id = int(parts[3])
        
        if user_id != callback_user_id:
            await query.answer("❌ This is not your search!", show_alert=True)
            return
        
        if user_id not in user_sessions:
            await query.edit_message_text("❌ Search session expired. Please start a new search.")
            return
        
        session = user_sessions[user_id]
        
        if result_index >= len(session['results']):
            await query.answer("❌ Invalid selection!", show_alert=True)
            return
        
        selected_result = session['results'][result_index]
        
        # Update message to show downloading status
        emoji = "🎵" if download_type == 'song' else "🎬"
        await query.edit_message_text(
            f"{emoji} **Downloading:** `{selected_result['title']}`\n\n⏳ Please wait, this may take a few minutes...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Download the media
            media_type = 'audio' if download_type == 'song' else 'video'
            file_path = await downloader.download_media(selected_result['url'], media_type, user_id)
            
            if not file_path or not os.path.exists(file_path):
                await query.edit_message_text("❌ Download failed. The video might be unavailable or restricted.")
                return
            
            # Check file size (Telegram limit is ~50MB for bots)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await query.edit_message_text("❌ File is too large to send via Telegram (>50MB). Please try a shorter video or song.")
                # Clean up the file
                try:
                    os.remove(file_path)
                except:
                    pass
                return
            
            # Send the file
            await query.edit_message_text(f"📤 Uploading {media_type}...")
            
            with open(file_path, 'rb') as file:
                if download_type == 'song':
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=file,
                        title=selected_result['title'],
                        performer=selected_result.get('uploader', 'Unknown'),
                        caption=f"🎵 **{selected_result['title']}**\n👤 **By:** {selected_result.get('uploader', 'Unknown')}"
                    )
                else:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=file,
                        caption=f"🎬 **{selected_result['title']}**\n👤 **By:** {selected_result.get('uploader', 'Unknown')}"
                    )
            
            # Success message
            await query.edit_message_text(f"✅ Successfully downloaded and sent: `{selected_result['title']}`", parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Download/upload error: {e}")
            await query.edit_message_text("❌ An error occurred during download or upload. Please try again.")
        
        finally:
            # Clean up: remove the downloaded file and user directory
            try:
                if 'file_path' in locals() and file_path and os.path.exists(file_path):
                    os.remove(file_path)
                
                # Remove user directory if empty
                user_dir = os.path.join(DOWNLOADS_DIR, str(user_id))
                if os.path.exists(user_dir) and not os.listdir(user_dir):
                    os.rmdir(user_dir)
                    
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            # Clean up user session
            if user_id in user_sessions:
                del user_sessions[user_id]

def cleanup_downloads():
    """Clean up old download directories"""
    try:
        if os.path.exists(DOWNLOADS_DIR):
            # Remove all subdirectories and files
            for item in os.listdir(DOWNLOADS_DIR):
                item_path = os.path.join(DOWNLOADS_DIR, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

async def main():
    """Main function to run the bot"""
    # Create downloads directory
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    
    # Clean up any existing downloads
    cleanup_downloads()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("song", song_command))
    application.add_handler(CommandHandler("vid", vid_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start the bot
    logger.info("Starting YouTube Downloader Bot...")
    
    try:
        await application.run_polling(drop_pending_updates=True)
    finally:
        # Clean up on shutdown
        await downloader.close_session()
        cleanup_downloads()

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}"

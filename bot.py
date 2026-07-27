import os
import tempfile
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from bundler import process_zip_file

load_dotenv()

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEB_APP_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'codebase-bundler-app-production.up.railway.app')
WEB_APP_URL = os.environ.get('WEB_APP_URL', f"https://{WEB_APP_DOMAIN}")

# In-memory storage for bundled texts (key: str(message_id))
CACHE_MAX_SIZE = 100
RESULT_CACHE = {}

def cache_result(key: str, data: dict):
    if len(RESULT_CACHE) >= CACHE_MAX_SIZE:
        keys_to_remove = list(RESULT_CACHE.keys())[:20]
        for k in keys_to_remove:
            RESULT_CACHE.pop(k, None)
    RESULT_CACHE[key] = data

def format_bytes(size):
    if size < 1024:
        return f"{size} Bytes"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    else:
        return f"{size / (1024 * 1024):.2f} MB"

def create_bot():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN environment variable not set. Bot disabled.")
        return None

    bot = telebot.TeleBot(TOKEN)

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        welcome_text = (
            "👋 **Welcome to the Project Context Bundler Bot!**\n\n"
            "Upload any GitHub repository **.zip** file here, and I will instantly bundle "
            "it into a single `project_context.txt` file ready for AI models!\n\n"
            "⚡ **Features:**\n"
            "- Ignores `node_modules`, `.git`, `venv`, `__pycache__`, & binary files\n"
            "- Formats clean file headers for ChatGPT, Claude, & Gemini\n"
            "- 📥 **Download** & 📋 **Copy** buttons included right in chat!\n\n"
            "📤 **Send any .zip file to get started!**"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 Web App", url=WEB_APP_URL))
        bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=markup)

    @bot.message_handler(content_types=['document'])
    def handle_document(message):
        doc = message.document
        if not doc.file_name.lower().endswith('.zip'):
            bot.reply_to(message, "⚠️ Please upload a valid **.zip** archive file.", parse_mode="Markdown")
            return

        status_msg = bot.reply_to(message, "⏳ Downloading and processing your project `.zip` file...")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            tmp_path = tmp_file.name

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)

            with open(tmp_path, 'wb') as f:
                f.write(downloaded_bytes)

            result = process_zip_file(tmp_path)

            text_content = result['text']
            file_count = result['file_count']
            total_lines = result['total_lines']
            total_bytes = result['total_bytes']

            summary = (
                "✅ **Project Context Bundled Successfully!**\n\n"
                f"📁 **Files Bundled:** `{file_count:,}`\n"
                f"📝 **Total Lines:** `{total_lines:,}`\n"
                f"📦 **Context Size:** `{format_bytes(total_bytes)}`\n\n"
                "👇 **Tap below to Download or Copy your context:**"
            )

            # Store result in cache
            cache_id = str(message.message_id)
            cache_result(cache_id, {
                'text': text_content,
                'filename': doc.file_name,
                'summary': summary
            })

            # Create Inline Keyboard with Download, Copy, & Web App buttons
            markup = InlineKeyboardMarkup(row_width=2)
            btn_download = InlineKeyboardButton("📥 Download .txt", callback_data=f"dl_{cache_id}")
            btn_copy = InlineKeyboardButton("📋 Copy Context", callback_data=f"copy_{cache_id}")
            btn_web = InlineKeyboardButton("🌐 Open Web App", url=WEB_APP_URL)
            
            markup.add(btn_download, btn_copy)
            markup.add(btn_web)

            # Send document file with Inline Keyboard buttons
            output_tmp = os.path.join(tempfile.gettempdir(), "project_context.txt")
            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                bot.send_document(
                    message.chat.id,
                    doc_file,
                    caption=summary,
                    parse_mode="Markdown",
                    reply_to_message_id=message.message_id,
                    reply_markup=markup
                )

            # Clean up output file
            if os.path.exists(output_tmp):
                os.remove(output_tmp)

            # Delete status message
            bot.delete_message(message.chat.id, status_msg.message_id)

        except Exception as e:
            bot.edit_message_text(f"❌ Error processing zip file: {str(e)}", message.chat.id, status_msg.message_id)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        if call.data.startswith("copy_"):
            cache_id = call.data.replace("copy_", "")
            cached = RESULT_CACHE.get(cache_id)

            if not cached:
                bot.answer_callback_query(call.id, "⚠️ Context expired or not found. Please re-upload your zip file.", show_alert=True)
                return

            text_content = cached['text']
            bot.answer_callback_query(call.id, "📋 Generating copyable text block...", show_alert=False)

            # Telegram message length limit is 4096.
            if len(text_content) <= 3800:
                copy_msg = (
                    "📋 **Tap the code block below to copy:**\n\n"
                    f"```text\n{text_content}\n```"
                )
            else:
                snippet = text_content[:3500]
                copy_msg = (
                    "📋 **Tap code block below to copy (First 3.5K chars preview):**\n\n"
                    f"```text\n{snippet}\n```\n\n"
                    "ℹ️ *Note: Full context is in the downloaded `project_context.txt` file attached above!*"
                )

            bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        elif call.data.startswith("dl_"):
            cache_id = call.data.replace("dl_", "")
            cached = RESULT_CACHE.get(cache_id)

            if not cached:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload your zip file.", show_alert=True)
                return

            bot.answer_callback_query(call.id, "📥 Preparing download file...", show_alert=False)

            text_content = cached['text']
            output_tmp = os.path.join(tempfile.gettempdir(), "project_context.txt")
            with open(output_tmp, "w", encoding="utf-8") as f:
                f.write(text_content)

            with open(output_tmp, "rb") as doc_file:
                bot.send_document(
                    call.message.chat.id,
                    doc_file,
                    caption="📥 **Here is your `project_context.txt` file:**",
                    parse_mode="Markdown",
                    reply_to_message_id=call.message.message_id
                )

            if os.path.exists(output_tmp):
                os.remove(output_tmp)

    return bot

def run_bot():
    bot = create_bot()
    if bot:
        print("Starting Telegram Bot polling loop...")
        bot.infinity_polling()

if __name__ == '__main__':
    run_bot()

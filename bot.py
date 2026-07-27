import os
import tempfile
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from bundler import process_zip_file
from store import save_bundle, get_bundle

load_dotenv()

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

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
            "- 📋 **1-Tap Copy** & 📥 **Download** directly inside Telegram chat!\n\n"
            "📤 **Send any .zip file to get started!**"
        )
        bot.reply_to(message, welcome_text, parse_mode="Markdown")

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

            # Save bundle into shared store
            bundle_id = save_bundle(
                text=text_content,
                file_count=file_count,
                total_lines=total_lines,
                total_bytes=total_bytes,
                filename=doc.file_name
            )

            summary = (
                "✅ **Project Context Bundled Successfully!**\n\n"
                f"📁 **Files Bundled:** `{file_count:,}`\n"
                f"📝 **Total Lines:** `{total_lines:,}`\n"
                f"📦 **Context Size:** `{format_bytes(total_bytes)}`\n\n"
                "👇 **Tap below to Copy or Download directly in chat:**"
            )

            # Create Inline Keyboard with Telegram chat buttons only (No external windows!)
            markup = InlineKeyboardMarkup(row_width=2)
            btn_copy = InlineKeyboardButton("📋 Copy Context", callback_data=f"copy_{bundle_id}")
            btn_download = InlineKeyboardButton("📥 Download .txt", callback_data=f"dl_{bundle_id}")
            
            markup.add(btn_copy, btn_download)

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
            bundle_id = call.data.replace("copy_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired or not found. Please re-upload your zip file.", show_alert=True)
                return

            text_content = bundle['text']
            bot.answer_callback_query(call.id, "📋 Sending copyable context into chat...", show_alert=False)

            CHUNK_SIZE = 3800
            total_len = len(text_content)

            if total_len <= CHUNK_SIZE:
                safe_text = text_content.replace("```", "'''")
                copy_msg = f"📋 **Tap code block below to copy:**\n\n```text\n{safe_text}\n```"
                bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)
            else:
                # Split cleanly by lines into ~3800 character chunks
                chunks = []
                lines = text_content.split('\n')
                current_chunk = []
                current_len = 0

                for line in lines:
                    line_len = len(line) + 1
                    if current_len + line_len > CHUNK_SIZE and current_chunk:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [line]
                        current_len = line_len
                    else:
                        current_chunk.append(line)
                        current_len += line_len
                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                total_parts = len(chunks)
                for idx, chunk in enumerate(chunks, 1):
                    safe_chunk = chunk.replace("```", "'''")
                    copy_msg = f"📋 **Part {idx}/{total_parts} (Tap code block below to copy):**\n\n```text\n{safe_chunk}\n```"
                    bot.send_message(call.message.chat.id, copy_msg, parse_mode="Markdown", reply_to_message_id=call.message.message_id)

        elif call.data.startswith("dl_"):
            bundle_id = call.data.replace("dl_", "")
            bundle = get_bundle(bundle_id)

            if not bundle:
                bot.answer_callback_query(call.id, "⚠️ Context expired. Please re-upload your zip file.", show_alert=True)
                return

            bot.answer_callback_query(call.id, "📥 Preparing download file...", show_alert=False)

            text_content = bundle['text']
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

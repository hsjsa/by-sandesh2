from random import SystemRandom
from string import ascii_letters, digits
from telegram.ext import CommandHandler
from threading import Thread
from time import sleep
from telegram import InlineKeyboardMarkup, ParseMode, InlineKeyboardButton
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.message_utils import sendMessage, sendMarkup, deleteMessage, delete_all_messages, update_all_messages, sendStatusMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.status_utils.clone_status import CloneStatus
from bot import dispatcher, MIRROR_LOGS, LOGGER, CLONE_LIMIT, STOP_DUPLICATE, download_dict, download_dict_lock, Interval
from bot.helper.ext_utils.bot_utils import is_url, get_readable_file_size, is_gdrive_link, is_gdtot_link, new_thread
from bot.helper.mirror_utils.download_utils.direct_link_generator import gdtot
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException


def _clone(message, bot, multi=0):
    args = message.text.split(" ", maxsplit=1)
    reply_to = message.reply_to_message
    link = ''
    if len(args) > 1:
        link = args[1]
        if link.isdigit():
            multi = int(link)
            link = ''
        elif message.from_user.username:
            tag = f"@{message.from_user.username}"
        else:
            tag = message.from_user.mention_html(message.from_user.first_name)
    if reply_to is not None:
        if len(link) == 0:
            link = reply_to.text
        if reply_to.from_user.username:
            tag = f"@{reply_to.from_user.username}"
        else:
            tag = reply_to.from_user.mention_html(reply_to.from_user.first_name)
    is_gdtot = is_gdtot_link(link)
    if is_gdtot:
        try:
            msg = sendMessage(f"⚙️ 𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐢𝐧𝐠: <code>{link}</code>", bot, message)
            link = gdtot(link)
            deleteMessage(bot, msg)
        except DirectDownloadLinkException as e:
            deleteMessage(bot, msg)
            return sendMessage(str(e), bot, message)
    if is_gdrive_link(link):
        gd = GoogleDriveHelper()
        res, size, name, files = gd.helper(link)
        if res != "":
            return sendMessage(res, bot, message)
        if STOP_DUPLICATE:
            LOGGER.info('Checking File/Folder if already in Drive...')
            smsg, button = gd.drive_list(name, True, True)
            if smsg:
                msg3 = "File/Folder is already available in Drive.\nHere are the search results:"
                return sendMarkup(msg3, bot, message, button)
        if CLONE_LIMIT is not None:
            LOGGER.info('Checking File/Folder Size...')
            if size > CLONE_LIMIT * 1024**3:
                msg2 = f'<b>Failed, Clone limit is</b> {CLONE_LIMIT}GB.\n<b>Your File/Folder size is</b> {get_readable_file_size(size)}.'
                return sendMessage(msg2, bot, message)
        if multi > 1:
            sleep(2)
            nextmsg = type('nextmsg', (object, ), {'chat_id': message.chat_id, 'message_id': message.reply_to_message.message_id + 1})
            nextmsg = sendMessage(args[0], bot, nextmsg)
            nextmsg.from_user.id = message.from_user.id
            multi -= 1
            sleep(2)
            Thread(target=_clone, args=(nextmsg, bot, multi)).start()
        if files <= 20:
            msg = sendMessage(f"⚙️ 𝐂𝐥𝐨𝐧𝐢𝐧𝐠: <code>{link}</code>", bot, message)
            result, button = gd.clone(link)
            deleteMessage(bot, msg)
        else:
            drive = GoogleDriveHelper(name)
            gid = ''.join(SystemRandom().choices(ascii_letters + digits, k=12))
            clone_status = CloneStatus(drive, size, message, gid)
            with download_dict_lock:
                download_dict[message.message_id] = clone_status
            sendStatusMessage(message, bot)
            result, typ , folders , button = drive.clone(link)
            with download_dict_lock:
                del download_dict[message.message_id]
                count = len(download_dict)
            try:
                if count == 0:
                    Interval[0].cancel()
                    del Interval[0]
                    delete_all_messages()
                else:
                    update_all_messages()
            except IndexError:
                pass
        cc = f'\n\n<b>cc: </b>{tag}'
        if button in ["cancelled", ""]:
            sendMessage(f"{tag} {result}", bot, message)
        else:
            sendMarkup(result + cc, bot, message, button)
        if is_gdtot:
            gd.deletefile(link)
        LOGGER.info(f"Cloning Done: {name}")

        # Clone Logs
        mesg = message.text.split('\n')
        message_args = mesg[0].split(' ', maxsplit=1)
        if MIRROR_LOGS:
            try:
                source_link = message_args[1]
                reply_to = message.reply_to_message
                sourceclonemsg = f"<b>#Cloned</b>\n"
                sourceclonemsg += f"\n━━━━━━━━━━━━━━━━━━━━━━"
                sourceclonemsg += f'\n<b>Source Url</b>: <b><a href="{source_link}">Here</a></b>'
                sourceclonemsg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
                sourceclonemsg += f"ㅤㅤ ㅤ   <b>«Cloned info»</b>\n"
                msg1 = f'\n{result} '
                msg1 += f'{cc}\n━━━━━━━━━━━━━━━━━━━━━━'
                for i in MIRROR_LOGS:
                    bot.sendMessage(i, text=sourceclonemsg + msg1, reply_markup=button, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except IndexError:
                pass
            if reply_to is not None:
                try:
                    reply_text = reply_to.text
                    if is_url(reply_text):
                        sourcelink = reply_text.strip()
                        sourceclonemsg2 = f'<b>#Cloned</b>\n'
                        sourceclonemsg2 += f"━━━━━━━━━━━━━━━━━━━━━━"
                        sourceclonemsg2 += f'\n<b>Source Url</b>: <b><a href="{sourcelink}">Here</a></b>'
                        sourceclonemsg2 += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
                        sourceclonemsg2 += f"ㅤㅤ ㅤ   <b>«Cloned info»</b>\n"
                        msg2 = f'\n{result} '
                        msg2 += f'{cc}\n━━━━━━━━━━━━━━━━━━━━━━'
                        for i in MIRROR_LOGS:
                            bot.sendMessage(chat_id=i, text=sourceclonemsg2 + msg2 , reply_markup=button, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except TypeError:
                    pass

    else:
        sendMessage('<b>Send Gdrive or gdtot link along with command or by replying to the link by command</b>', bot, message)

@new_thread
def cloneNode(update, context):
    _clone(update.message, context.bot)

clone_handler = CommandHandler(BotCommands.CloneCommand, cloneNode, filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
dispatcher.add_handler(clone_handler)

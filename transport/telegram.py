import asyncio, time
from telegram.ext import Application, MessageHandler, filters
import audit
from config import TOKEN, ALLOWED, VOICE, MAX_VOICE_BYTES
from transport.base import Transport, Message
from telegram.error import NetworkError
import collections

class TelegramTransport(Transport):
    def __init__(self):
        self.q: asyncio.Queue[Message] = asyncio.Queue()
        self.app = (Application.builder().token(TOKEN)
                    .connect_timeout(20).read_timeout(30).write_timeout(30).pool_timeout(20)
                    .get_updates_connect_timeout(20).get_updates_read_timeout(40)
                    .build())
        flt = filters.ChatType.PRIVATE & ((filters.TEXT & ~filters.COMMAND) | filters.VOICE)
        self.app.add_handler(MessageHandler(flt, self._on_update))
        self._seen = collections.deque(maxlen=200)

    async def _on_update(self, update, ctx):
        if update.update_id in self._seen:
            return
        self._seen.append(update.update_id)
        m, u = update.effective_message, update.effective_user
        if u is None or u.id not in ALLOWED:
            audit.log("reject", user_id=u.id if u else None)
            return
        if m.voice:
            if (m.voice.file_size or 0) > MAX_VOICE_BYTES:
                audit.log("voice_too_large", user_id=u.id, size=m.voice.file_size)
                await m.reply_text("voice too large")
                return
            f = await m.voice.get_file()
            path = VOICE / f"{int(time.time())}_{u.id}.ogg"
            await f.download_to_drive(path)
            msg = Message("telegram", str(u.id), audio=path)
        else:
            msg = Message("telegram", str(u.id), text=m.text)
        audit.log("recv", user_id=u.id, kind="voice" if msg.audio else "text")
        await self.q.put(msg)

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    async def receive(self) -> Message:
        return await self.q.get()

    async def send(self, to: str, text: str):
        for i in range(4):
            try:
                await self.app.bot.send_message(chat_id=int(to), text=text[:4000])
                return
            except NetworkError:        # TimedOut is a subclass
                if i == 3:
                    raise
                await asyncio.sleep(2 * (i + 1))
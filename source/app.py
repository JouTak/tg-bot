import threading
from source.scheduler import poll_new_tasks
from source.connections.bot_factory import bot
import source.handlers
import source.callbacks

def run():
    t = threading.Thread(target=poll_new_tasks, daemon=True)
    t.start()
    bot.polling()

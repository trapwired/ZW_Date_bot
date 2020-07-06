import configparser
import logging
import datetime
import time

import telepot
# from scheduler import SchedulerHandler
# import ASVZ_Crawler


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser):
        self.config = config
        self.api_config = api_config

        self.bot = telepot.Bot(self.api_config["API"]["key"])

        # self.scheduler_handler = SchedulerHandler(self.bot)

    def handle(self, msg: dict):
        # Get fields from message
        chat_id = msg['chat']['id']
        command = msg['text']
        command = command.lower()

        logging.info(
            f"Got command: {command} from {chat_id}")

        # Comparing the incoming message to send a reply according to it
        if command == '/hi':
            self.bot.sendMessage(chat_id, str("Hi back!"))
        elif command == '/start':
            self.bot.sendMessage(chat_id, 'Hi there! \n I am the Züri West Manager')
        else:
            self.bot.sendMessage(chat_id, command)

    def start(self):
        self.bot.message_loop(self.handle)
        logging.info("Bot started")


def main():
    # config File
    config = configparser.RawConfigParser()
    config.read('config.ini', encoding='utf8')

    api_config = configparser.RawConfigParser()
    api_config.read('api.ini', encoding='utf8')

    # Logging
    logging_arguments = dict()
    logging_arguments["format"] = config["Logging"]["format"]
    logging_arguments["level"] = logging.getLevelName(
        config["Logging"]["level"])
    if config["Logging"].getboolean("to_file"):
        logging_arguments["filename"] = config["Logging"]['logfile']
    logging.basicConfig(**logging_arguments)

    # Start botting
    bot = ZWTelegramBot(config, api_config)
    bot.start()

    while True:
        # bot.scheduler_handler.run_schedule()
        time.sleep(10)


if __name__ == "__main__":
    main()

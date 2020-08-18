import configparser
import logging
import datetime
import time
import os
from DatabaseHandler import DatabaseHandler

import telepot
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
# from scheduler import SchedulerHandler


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, db_config: configparser.RawConfigParser):
        self.config = config
        self.api_config = api_config

        self.bot = telepot.Bot(self.api_config["API"]["key"])

        self.database_handler = DatabaseHandler(db_config)

        # self.scheduler_handler = SchedulerHandler(self.bot)

    def handle(self, msg: dict):
        content_type, chat_type, chat_id = telepot.glance(msg)
        # print(msg)
        if content_type == 'text':
            # Get fields from message
            command = msg['text']
            # convert command to lowerCase
            command = command.lower()
            
            logging.info(f"BOT - Got command: {command} from {chat_id}")


            # Comparing the incoming message to send a reply according to it
            if command == '/hi':
                self.bot.sendMessage(chat_id, str("Hi back!"))
            elif command == '/start':
                first_name = msg['from']['first_name']
                last_name = msg['from']['last_name']
                # add player to Database if not already added
                if not self.database_handler.player_present(chat_id):
                    self.database_handler.insert_new_player(first_name, last_name, chat_id)
                k = ReplyKeyboardMarkup(keyboard=[['/start', '/help', '/stats'], ['/games', '/finish']], resize_keyboard=True)
                self.bot.sendMessage(chat_id, 'Hi there! \n I am the Züri West Manager \n These are my functions', reply_markup=k)
            elif command == '/key':
                k = ReplyKeyboardMarkup(keyboard=[['Yes', 'No', 'Maybe'], ['previous Games']], one_time_keyboard=True, resize_keyboard=True)
                msg = self.bot.sendMessage(chat_id, 'Handball Game, 17.08.2020 - Saalsporthalle - TV Wil', reply_markup=k)
                # msg_ident = telepot.message_identifier(msg)
                # self.bot.editMessageReplyMarkup(msg_ident, reply_markup=None)
                # maybe add summary at end 
            elif command == '/del_k': 
                self.bot.sendMessage(chat_id, 'Deleting keyboard', reply_markup=ReplyKeyboardRemove())
            else:
                self.bot.sendMessage(chat_id, command)
        else:
            logging.info(f"BOT - Got {content_type} from {chat_id}")


    def start(self):
        self.bot.message_loop(self.handle)
        logging.info("BOT - Bot started")


def main():
    # config File
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'config.ini'), encoding='utf8')

    api_config = configparser.RawConfigParser()
    api_config.read(os.path.join(path, 'api.ini'), encoding='utf8')

    db_config = configparser.RawConfigParser()
    db_config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')

    # Logging
    logging_arguments = dict()
    logging_arguments["format"] = config['Logging']["format"]
    logging_arguments["level"] = logging.getLevelName(
        config["Logging"]["level"])
    if config["Logging"].getboolean("to_file"):
        logging_arguments["filename"] = config["Logging"]['logfile']
    logging.basicConfig(**logging_arguments)

    # Start botting
    bot = ZWTelegramBot(config, api_config, db_config)
    bot.start()

    while True:
        # bot.scheduler_handler.run_schedule()
        time.sleep(10)


if __name__ == "__main__":
    main()

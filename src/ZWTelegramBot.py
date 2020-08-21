import configparser
import logging
import datetime
import time
import os
from DatabaseHandler import DatabaseHandler
from Enum import Enum

import telepot
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
# from scheduler import SchedulerHandler


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, db_config: configparser.RawConfigParser):
        self.config = config
        self.api_config = api_config

        self.bot = telepot.Bot(self.api_config["API"]["key"])
        self.database_handler = DatabaseHandler(db_config)
        # self.states = Enum(['START', 'OVERVIEW', 'SELECT'])
        self.state_map = dict() # -1: Start, Overview, any other positive number: represents game is beeing edited

        # self.scheduler_handler = SchedulerHandler(self.bot)

    def handle(self, msg: dict):
        content_type, chat_type, chat_id = telepot.glance(msg)

        # private chat reply
        if chat_type == 'private':
            if content_type == 'text':
                # Get fields from message
                command = msg['text']
                # convert command to lowerCase
                command = command.lower()
                
                logging.info(f"BOT - Got command: {command} from {chat_id}")


                # Comparing the incoming message to send a reply according to it
                if command == '/del_k': 
                    reply_text = 'Deleting keyboard'
                    reply_keyboard = self.get_keyboard('remove')
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                elif command == '/help':
                    reply_text = self.get_help()
                    reply_keyboard = self.get_keyboard('default')
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                elif command == '/hi':
                    first_name = msg['from']['first_name']
                    reply_text = f"Hi {first_name}"
                    self.bot.sendMessage(chat_id, reply_text)

                elif command == '/start':
                    # first time (only time) of issued start command
                    if chat_id not in self.state_map:
                        first_name = msg['from']['first_name']
                        last_name = msg['from']['last_name']

                        # add chat_id to state_map
                        self.state_map[chat_id] = -1

                        # add player to Database if not already added
                        if not self.database_handler.player_present(chat_id):
                            self.database_handler.insert_new_player(first_name, last_name, chat_id)

                    # send reply
                    reply_text = 'Hi there! \nI am the Züri West Manager \nThese are my functions \nWhen your are ready, click on \'/edit_games\' to mark your presence in Züri West handball games'
                    reply_keyboard = self.get_keyboard('default')
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                elif command == '/stats':
                    reply_text = 'The stats for our next game are:\n' + self.get_stats_next_game()
                    self.bot.sendMessage(chat_id, reply_text)

                else:
                    # TODO deal with any other message: maybe send /help?
                    self.bot.sendMessage(chat_id, command)
            else:
                logging.info(f"BOT - Got {content_type} from {chat_id}")

        # group chat reply
        elif chat_type == 'group':
            if content_type == 'text':
                command = msg['text']
                logging.info(f"BOT - Group-Message - Got {command} from {chat_id}")
                # it concerns the bot - so answer
                if command.startswith('@Zuri_West_Manager_Bot'):
                    command = command[23:]
                    if command == '/stats' or command == 'stats':
                        self.bot.sendMessage(chat_id, 'The stats for our next game are:\n' + self.get_stats_next_game())

            else:
                logging.info(f"BOT - Got {content_type} from {chat_id}")


    def start(self):
        self.bot.message_loop(self.handle)
        logging.info("BOT - Bot started")


    def get_stats_next_game(self):
        # TODO pretty print stats for the next game
        return 'TODO'

    
    def get_help(self):
        # TODO pretty print all possible commands and their function
        return 'TODO'


    def get_keyboard(self, kind: str):
        keyboard = None
        if kind == 'select':
            keyboard = ReplyKeyboardMarkup(keyboard=[['Yes', 'No', 'Unsure'], ['Overview', 'continue later']], resize_keyboard=True, one_time_keyboard=True)
        elif kind == 'default':
            # TODO remove /start
            keyboard = ReplyKeyboardMarkup(keyboard=[['/start', '/help', '/stats'], ['/edit_games']], resize_keyboard=True)
        elif kind == 'remove':
            keyboard = ReplyKeyboardRemove()
        return keyboard


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

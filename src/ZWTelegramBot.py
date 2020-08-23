import configparser
import logging
import datetime
import time
import os
from DatabaseHandler import DatabaseHandler
import utility as util
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
        self.state_map = self.database_handler.init_state_map() # -1: Start, 0 = Overview, any other positive number: represents game is beeing edited (from chat_id to int)
        # self.scheduler_handler = SchedulerHandler(self.bot)

    def handle(self, msg: dict):
        content_type, chat_type, chat_id = telepot.glance(msg)

        # private chat reply
        if chat_type == 'private':

            first_name = msg['from']['first_name']

            if content_type == 'text':

                command = msg['text']
                # convert command to lowerCase
                command = command.lower()
                
                logging.info(f"BOT - Got command: {command} from {chat_id}")
                
                if chat_id in self.state_map:

                    if self.state_map[chat_id] < 0:
                        if command == '/edit_games':
                            reply_text = self.get_reply_text('edit_games', first_name)
                            reply_keyboard = self.get_keyboard('overview', chat_id)
                            self.update_state_map(chat_id, 0)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard, parse_mode= 'MarkdownV2')
                     
                        elif command == '/help':
                            self.update_state_map(chat_id,-1)
                            reply_text = self.get_reply_text('help', first_name)
                            reply_keyboard = self.get_keyboard('default', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                        elif command == '/hi' or command == 'hi':
                            reply_text = self.get_reply_text('hi', first_name)
                            self.bot.sendMessage(chat_id, reply_text)

                        elif command == '/start':
                            reply_text = self.get_reply_text('start', first_name)
                            reply_keyboard = self.get_keyboard('default', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                        elif command == '/stats':
                            reply_text = self.get_reply_text('stats', first_name)
                            self.bot.sendMessage(chat_id, reply_text, parse_mode= 'MarkdownV2')


                    elif self.state_map[chat_id] == 0:
                        # chat_id choose a game to edit attendance
                        current_game_id = self.database_handler.get_game_id(command[:10])
                        if command == 'continue later':
                            self.update_state_map(chat_id,-1)
                            reply_text = self.get_reply_text('continue later', first_name)
                            reply_keyboard = self.get_keyboard('default', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                        
                        elif current_game_id >= 0:
                            self.update_state_map(chat_id,current_game_id)
                            # assemble reply with select-keyboard
                            reply_text = self.get_reply_text('selection', first_name)
                            reply_keyboard = self.get_keyboard('select', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                        else:
                            # deal with Game not found Error
                            logging.warning(f"Game not found {command}")

                    elif self.state_map[chat_id] > 0:
                        # chat_id choose YES/NO/UNSURE for the game with ID self.state_map[chat_id]
                        if command.upper() in util.ATTENDANCE:
                            self.database_handler.edit_game_attendance(self.state_map[chat_id], command, chat_id)
                            # now send overview again
                            self.update_state_map(chat_id, -1)
                            msg['text'] = '/edit_games'
                            self.handle(msg)
                        elif command == 'overview':
                            self.update_state_map(chat_id,-1)
                            msg['text'] = '/edit_games'
                            self.handle(msg)
                        elif command == 'continue later':
                            self.update_state_map(chat_id,-1)
                            reply_text = self.get_reply_text('continue later', first_name)
                            reply_keyboard = self.get_keyboard('default', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)


                else: # chat_id not in state_map

                    if command == '/start':
                        # add player to Database if not already added
                        if not self.database_handler.player_present(chat_id):
                            first_name = msg['from']['first_name']
                            last_name = msg['from']['last_name']
                            self.database_handler.insert_new_player(chat_id, first_name, last_name)
                        self.update_state_map(chat_id,-1)

                    # send reply
                    reply_text = self.get_reply_text('start', 'there')
                    reply_keyboard = self.get_keyboard('default', chat_id)
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                

                # else:
                    # TODO deal with any other message: maybe send /help?
                    # self.bot.sendMessage(chat_id, command)

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
                        self.bot.sendMessage(chat_id, 'The stats for our next game are:\n' + self.get_reply_text('stats', 'Group'), parse_mode= 'MarkdownV2')

            else:
                logging.info(f"BOT - Got {content_type} from {chat_id}")


    def start(self):
        self.bot.message_loop(self.handle)
        logging.info("BOT - Bot started")

    
    def get_reply_text(self, kind: str, first_name: str):
        reply = ''
        if kind == 'help':
            reply = f"Hi {first_name} - here are my available commands\n/edit_games: lets you edit your games\n/help: shows the list of available commands\n/stats: shows the status for our next game\n"

        elif kind == 'edit_games':
            reply = "Click on the game to change you attendance \\- in brackets you see your current status \\ \n*TIPP: the list ist scrollable*"

        elif kind == 'hi':
            reply = f"Hi {first_name}"

        elif kind == 'start':
            reply = f"Hi {first_name}! \nI am the Züri West Manager \nBelow you see the available commands \nWhen your are ready, click on \'/edit_games\' to mark your presence in Züri West handball games"

        elif kind == 'stats':
            reply = self.database_handler.get_stats_next_game()

        elif kind == 'continue later':
            reply = f"See ya, {first_name}"

        elif kind == 'selection':
            reply = 'Will you be there (YES), be absent (NO) or are not sure yet (UNSURE)?'

        return reply


    def get_keyboard(self, kind: str, chat_id: int):
        keyboard = None
        if kind == 'default':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/help', '/stats'], ['/edit_games']], resize_keyboard=True)
        elif kind == 'overview':
            buttons = self.database_handler.get_games_list_with_status(chat_id)
            keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
        elif kind == 'remove':
            keyboard = ReplyKeyboardRemove()
        elif kind == 'select':
            keyboard = ReplyKeyboardMarkup(keyboard=[['YES', 'NO', 'UNSURE'], ['Overview', 'continue later']], resize_keyboard=True, one_time_keyboard=True)

        return keyboard

    def update_state_map(self, chat_id: int, new_state: int):
        # update state in Players Table
        self.database_handler.update_state(chat_id, new_state)
        # update self.state_map
        self.state_map[chat_id] = new_state


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

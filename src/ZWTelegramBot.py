import configparser
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
import time
import os
import mariadb
import sys

from DatabaseHandler import DatabaseHandler
from Scheduler import SchedulerHandler

import utility as util

# telepot imports
import telepot
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, db_config: configparser.RawConfigParser, _logger):
        self.config = config
        self.api_config = api_config
        self.admin_chat_id = self.api_config["API"]["admin_chat_id"]
        self.logger = _logger
        self.logger.debug("LOGGER STARTED -----------------------------------")

        self.bot = telepot.Bot(self.api_config["API"]["key"])
        count = 0
        while count < 10:
            try:
                self.database_handler = DatabaseHandler(db_config, _logger)
                count = 10
            except mariadb.Error as err:
                time.sleep(10)
                count += 1
                if count > 9:
                    self.bot.sendMessage(self.admin_chat_id, f"ERROR: starting DB\n{err}")
                    sys.exit(1)
                    
        self.state_map = self.database_handler.init_state_map() 
        self.scheduler_handler = SchedulerHandler(api_config, self.bot, self.database_handler, _logger)

    def handle(self, msg: dict):
        content_type, chat_type, chat_id = telepot.glance(msg)

        # private chat reply
        if chat_type == 'private':
            # Access first and last name, check if exists to avoid dict-key error
            last_name = ' No Name Given'
            first_name =' No Name Given'
            if 'last_name' in msg['from'].keys():
                last_name = msg['from']['last_name'].capitalize()
            if 'first_name' in msg['from'].keys():
                first_name = msg['from']['first_name'].capitalize()

            if content_type == 'text':

                command = msg['text'].lower()
                
                self.logger.info(f"BOT - Got command: {command} from {chat_id}")
                
                if chat_id in self.state_map:
                    if self.state_map[chat_id] < 0:
                    # State: default, all commands can be executed

                        if command == '/edit_games':
                            reply_text = self.get_reply_text('edit_games', first_name)
                            reply_keyboard = self.get_keyboard('overview', chat_id)
                            self.update_state_map(chat_id, 0)
                            if reply_keyboard is None:
                                reply_text = self.get_reply_text('overview_no_games', first_name)
                                self.update_state_map(chat_id, -1)
                                reply_keyboard = self.get_keyboard('default', first_name)
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
                    # State: User is on 'overview' of games, expected answer is either a game or 'continue later'

                        game_date = command[:10]
                        current_game_id = self.database_handler.get_game_id(game_date)
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
                            self.logger.warning(f"Game not found, got {command}")

                    elif self.state_map[chat_id] > 0:
                        # State: Usure choosing YES/NO/UNSURE for the game with ID self.state_map[chat_id]
                        if util.status_is_valid(command):
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
                            self.database_handler.insert_new_player(chat_id, first_name, last_name)
                            self.update_state_map(chat_id,-1)

                            # send reply
                            reply_text = self.get_reply_text('start', 'there')
                            reply_keyboard = self.get_keyboard('default', chat_id)
                            self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                    
                    else:
                        reply_text = self.get_reply_text('init', 'there')
                        reply_keyboard = self.get_keyboard('init', chat_id)
                        self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                

                # else:
                    # TODO deal with any other message: maybe send /help?
                    # self.bot.sendMessage(chat_id, command)

            else:
                self.logger.info(f"BOT - Got {content_type} from {chat_id}")


        # group chat reply
        elif chat_type == 'group':
            if content_type == 'text':
                command = msg['text']
                self.logger.info(f"BOT - Group-Message - Got {command} from {chat_id}")
                # it concerns the bot - so answer
                if command.startswith('@Zuri_West_Manager_Bot'):
                    command = command[23:]
                    if command == '/stats' or command == 'stats':
                        self.bot.sendMessage(chat_id, 'The stats for our next game are:\n' + self.get_reply_text('stats', 'Group'), parse_mode= 'MarkdownV2')

            else:
                self.logger.info(f"BOT - Got {content_type} from {chat_id}")


    def start(self):
        self.bot.message_loop(self.handle)
        self.logger.info("BOT - Bot started")

    
    def get_reply_text(self, kind: str, first_name: str):
        reply = ''
        if kind == 'help':
            reply = f"Hi {first_name} - here are my available commands\n/edit_games: lets you edit your games\n/help: shows the list of available commands\n/stats: shows the status for our next game\n"

        elif kind == 'init':
            reply = f"Please try again by clicking on /start"

        elif kind == 'edit_games':
            reply = "Click on the game to change you attendance \\- in brackets you see your current status \\ \n*TIPP: the list ist scrollable*"

        elif kind == 'hi':
            reply = f"Hi {first_name}"

        elif kind == 'overview_no_games':
            reply = 'There are no upcoming games'

        elif kind == 'start':
            reply = f"Hi {first_name}! \nI am the Züri West Manager \nBelow you see the available commands \nWhen your are ready, click on \'/edit_games\' to mark your presence in Züri West handball games"

        elif kind == 'stats':
            reply = self.database_handler.get_stats_next_game()

        elif kind == 'continue later':
            reply = f"Cheerio, {first_name}"

        elif kind == 'selection':
            reply = 'Will you be there (YES), be absent (NO) or are not sure yet (UNSURE)?'

        return reply


    def get_keyboard(self, kind: str, chat_id: int):
        keyboard = None
        if kind == 'default':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/help', '/stats'], ['/edit_games']], resize_keyboard=True)
        elif kind == 'init':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/start']], resize_keyboard=True)
        elif kind == 'overview':
            buttons = self.database_handler.get_games_list_with_status(chat_id)
            if len(buttons) < 2:
                # either an error occured or there are no games in the future
                return None
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


def init_logger(config: configparser.RawConfigParser):
    logger = logging.getLogger(__name__)
    logHandler = TimedRotatingFileHandler(filename="/home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_logger.log", when="midnight")
    # format = '%(asctime)s %(filename)s(%(lineno)d) %(levelname)s %(message)s'
    formatter = logging.Formatter(fmt=config['Logging']["format"], datefmt='%d/%m/%Y %H:%M:%S')
    logHandler.setFormatter(formatter)
    logHandler.setLevel(config["Logging"]["level"])
    logger.addHandler(logHandler)
    return logger

def main():
    # config File
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'config.ini'), encoding='utf8')

    api_config = configparser.RawConfigParser()
    api_config.read(os.path.join(path, 'api.ini'), encoding='utf8')

    db_config = configparser.RawConfigParser()
    db_config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')

    ZW_logger = init_logger(config)

    # Logging
    logging_arguments = dict()
    logging_arguments["format"] = config['Logging']["format"]
    logging_arguments["level"] = logging.getLevelName(
        config["Logging"]["level"])
    if config["Logging"].getboolean("to_file"):
        logging_arguments["filename"] = config["Logging"]['logfile']
    logging.basicConfig(**logging_arguments)

    # Start botting
    bot = ZWTelegramBot(config, api_config, db_config, ZW_logger)
    bot.start()
    

    while True:
        bot.scheduler_handler.run_schedule()
        time.sleep(10)


if __name__ == "__main__":
    # today = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    # os.rename("/home/pi/Desktop/ZW_Date_bot/ZW_bot.log", f"/home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_{today}.log")
    main()
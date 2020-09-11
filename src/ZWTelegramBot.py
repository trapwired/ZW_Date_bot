import configparser
import datetime
import time
import os
import mariadb
import sys

import logging
from logging.handlers import TimedRotatingFileHandler

from DatabaseHandler import DatabaseHandler
from Scheduler import SchedulerHandler
from exceptions import NotifyUserException, NotifyAdminException

import utility as util

import telepot
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, db_config: configparser.RawConfigParser, _logger: logging.Logger):
        """initialize main class with bot, start all Handlers

        Args:
            config (configparser.RawConfigParser): configuration file for bot
            api_config (configparser.RawConfigParser): configuration file with secrets (Bot Token, admin_chat_id)
            db_config (configparser.RawConfigParser): configuration file for database handler
            _logger (logging.Logger): logger instance, will be passed to databaseHandler and scheduleHandler -> one logger for all classes
        """        

        # initialize fields
        self.config = config
        self.api_config = api_config
        self.admin_chat_id = int(self.api_config["API"]["admin_chat_id"])
        self.group_chat_id = self.api_config["API"]["group_chat_id"]
        
        # initialize logger 
        self.logger = _logger
        self.logger.info("start main\n\n")
        self.logger.info("Logger started")

        # start Bot
        self.bot = telepot.Bot(self.api_config["API"]["key"])

        # start DataBase Handler
        self.database_handler = self.init_databaseHandler(self.bot, db_config, api_config, _logger, self.admin_chat_id)

        # initialize lists / dicts
        self.user_whitelist = self.init_user_whitelist()
        self.state_map = self.database_handler.init_state_map() 
                    
        # start Scheduler Handler
        self.scheduler_handler = SchedulerHandler(api_config, self.bot, self.database_handler, _logger)
        self.scheduler_handler.send_reminder_at_8am(self.send_reminders)
        self.scheduler_handler.send_stats_to_group_chat(self.send_stats_to_group_chat)

        # testing - TO DELETE
        info = self.bot.sendMessage(self.admin_chat_id, 'testing custom keyboard', reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="One",callback_data='1'),InlineKeyboardButton(text="Two",callback_data='2'), InlineKeyboardButton(text="Three",callback_data='3')],
                                ]
                            ))
        self.messageID = info['message_id']
        

    def send_reminders(self):
        """send reminders to all unsure players for games in 5/6/7/12 days
        """
        try:
            # get all unsure players and their respective games (they are unsure at)
            player_to_messages_map = self.scheduler_handler.load_schedules()
        except NotifyAdminException as err:
            self.bot.sendMessage(self.admin_chat_id, f"loading schedules did not succeed - no scheduled messages today\n{err}")
        else:
            # loop through all pairs of players and game-strings
            for player_chat_id, games in player_to_messages_map.items():
                # assemble reminder text
                reminder_text = "Hey, we still need to know whether you will play in the following games:\n"
                button_list = []
                button_list.append(['continue later'])
                for game in games:
                    # add each pretty-printed game to reminder_text and button list
                    game_info = f"{util.make_datetime_pretty_str(game[0])} | {game[2]}"
                    reminder_text += f"{game_info}\n"
                    button_list.append([game_info])
                # assemble bot-reply (custom keyboard containing all games to still edit)
                reply_keyboard = self.get_keyboard('reminder_games', -1, button_list=button_list)
                self.bot.sendMessage(player_chat_id, reminder_text, reply_markup=reply_keyboard)
                self.update_state_map(player_chat_id, 0)
                

    def init_databaseHandler(self, bot: telepot.Bot, db_config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, _logger: logging.Logger, admin_chat_id: int):
        """initialize the DataBase Handler, retry 10 times on error, notify administrator otherwise and exit

        Args:
            bot (telepot.Bot): bot, used to notify the admin
            db_config (configparser.RawConfigParser):  provides the login credentials to the database
            api_config (configparser.RawConfigParser): provides the admin_chat_id
            _logger (logging.Logger): provides the logging facilities
            admin_chat_id (int): provide the admin_chat_id to the bot 

        Returns:
            DatabaseHandler: correctly initialized database Handler
        """

        count = 0
        while count < 10:
            try:
                database_handler = DatabaseHandler(bot, db_config, api_config, _logger)
                count = 10
            except mariadb.Error as err:
                time.sleep(1)
                count += 1
                if count > 9:
                    bot.sendMessage(admin_chat_id, f"ERROR: starting DB - BOT NOT RUNNING{err}")
                    sys.exit(1)
            except NotifyAdminException as err:
                bot.sendMessage(admin_chat_id, f"ERROR: starting DB - BOT NOT RUNNING{err}")
        return database_handler


    def init_user_whitelist(self):
        """load the user_ids saved in api_config to list for faster access

        Returns:
            list: A List containing all user id's allowed to exchange messages with the bot
        """
        user_list = self.api_config["API"]["user_whitelist"]
        user_whitelist = []
        user_whitelist.append(int(self.group_chat_id))
        user_list_split = user_list.split(',')
        for user_id in user_list_split:
            user_whitelist.append(user_id)
        return user_whitelist


    def handle(self, msg: dict):
        """Called each time a message is sent to the bot

        Args:
            msg (dict): parsed from reply-json of each message to bot
        """        

        content_type, chat_type, chat_id = telepot.glance(msg)

        # check if user in self.user_whitelist / authorized to use bot
        if chat_id in self.user_whitelist:

            # private chat reply
            if chat_type == 'private':

                try:
                    # Access first and last name, check if exists to avoid dict-key error
                    last_name = ' No Name Given'
                    first_name =' No Name Given'
                    if 'last_name' in msg['from'].keys():
                        last_name = msg['from']['last_name'].capitalize()
                    if 'first_name' in msg['from'].keys():
                        first_name = msg['from']['first_name'].capitalize()

                    # Bot got a text 
                    if content_type == 'text':

                        command = msg['text'].lower()
                        
                        self.logger.info(f"Got command: {command} from {chat_id}")
                        
                        # player was already chatting with bot
                        if chat_id in self.state_map:

                            # State: default, all commands can be executed
                            if self.state_map[chat_id] < 0:

                                if command == '/edit_games':
                                    self.update_state_map(chat_id, 0)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('edit_games', first_name)
                                    reply_keyboard = self.get_keyboard('overview', chat_id)
                                    if reply_keyboard is None:
                                        # there are no games in the future, reset State
                                        self.update_state_map(chat_id, -1)
                                        # Assemble reply
                                        reply_text = self.get_reply_text('overview_no_games', first_name)
                                        reply_keyboard = self.get_keyboard('default', first_name)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard, parse_mode= 'MarkdownV2')
                            
                                elif command == '/help':
                                    self.update_state_map(chat_id,-1)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('help', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                                elif command == '/hi' or command == 'hi':
                                    # Assemble reply
                                    reply_text = self.get_reply_text('hi', first_name)
                                    self.bot.sendMessage(chat_id, reply_text)

                                elif command == '/start':
                                    # Assemble reply
                                    reply_text = self.get_reply_text('start', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                                elif command == '/stats':
                                    # Assemble reply
                                    reply_text = self.get_reply_text('stats', first_name)
                                    self.bot.sendMessage(chat_id, reply_text, parse_mode= 'MarkdownV2')

                            # State: User is on 'overview' of games, expected answer is either a game or 'continue later'
                            elif self.state_map[chat_id] == 0:

                                if command == 'continue later':
                                    self.update_state_map(chat_id,-1)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                
                                else:
                                    # we possibly got a game, convert to game_id to change attendance in database
                                    game_date = command[:16]
                                    current_game_id = self.database_handler.get_game_id(game_date)
                                    if current_game_id >= 0:
                                        self.update_state_map(chat_id,current_game_id)
                                        # assemble reply with select-keyboard
                                        reply_text = self.get_reply_text('selection', first_name)
                                        reply_keyboard = self.get_keyboard('select', chat_id)
                                        self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    else:
                                        # Game not in DataBase, ignore input
                                        self.logger.warning(f"Game not found, got {command}")
                                        self.update_state_map(chat_id, -1)
                                        msg['text'] = '/help'
                                        self.handle(msg)


                            elif self.state_map[chat_id] > 0:
                                # State: User choosing YES/NO/UNSURE for the game with ID self.state_map[chat_id]
                                if util.status_is_valid(command):
                                    self.database_handler.edit_game_attendance(self.state_map[chat_id], command, chat_id)
                                    # send overview again
                                    self.update_state_map(chat_id, -1)
                                    msg['text'] = '/edit_games'
                                    self.handle(msg)

                                elif command == 'overview':
                                    self.update_state_map(chat_id,-1)
                                    msg['text'] = '/edit_games'
                                    self.handle(msg)

                                elif command == 'continue later':
                                    self.update_state_map(chat_id,-1)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                else:
                                    self.update_state_map(chat_id, -1)
                                    msg['text'] = '/help'
                                    self.handle(msg)


                        else: 
                        # chat_id not in state_map
                            
                            if command == '/start':
                                # add player_chat_id to Database if not already added
                                if not self.database_handler.player_present(chat_id):
                                    self.database_handler.insert_new_player(chat_id, first_name, last_name)
                                    self.state_map[chat_id] = -1 
                                    # send reply
                                    reply_text = self.get_reply_text('start')
                                    reply_keyboard = self.get_keyboard('default', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            else:
                                reply_text = self.get_reply_text('init')
                                reply_keyboard = self.get_keyboard('init', chat_id)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                    # got something different from text, ignore
                    else:
                        self.logger.info(f"Got {content_type} from {chat_id}")

                except NotifyUserException as nuException:
                    # something went wrong
                    self.update_state_map(chat_id, -1)
                    # send error to admin
                    self.bot.sendMessage(self.admin_chat_id, f"Error in executing the following query:\n{nuException}")
                    # Assemble reply, notify user an error occured
                    reply_text = self.get_reply_text('error', first_name)
                    reply_keyboard = self.get_keyboard('default', chat_id)
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)


            # group chat reply
            elif chat_type in ['group', 'supergroup']:
                try:
                    if content_type == 'text':
                        command = msg['text']
                        self.logger.info(f"Group-Message - Got {command} from {chat_id}")

                        if command.startswith('@Zuri_West_Manager_Bot'):
                            # directly adressed at the bot, answer
                            command = command[23:]
                            if 'stats' in command:
                                self.bot.sendMessage(chat_id, 'The stats for our next game are:\n' + self.get_reply_text('stats'), parse_mode= 'MarkdownV2')

                    else:
                        self.logger.info(f"Got {content_type} from Group-chat ({chat_id})")

                except (NotifyUserException, NotifyAdminException) as nuException:
                    self.bot.sendMessage(self.admin_chat_id, f"Error in executing the following query:\n{nuException}")


        # user not in whitelist
        else:

            if chat_id > 0:
                # message from user, check if in group
                chatMemberInformation = self.bot.getChatMember(self.group_chat_id, chat_id)
                statusInformation = chatMemberInformation['status']
                isMember = bool(util.is_member_of_group(statusInformation))
                if isMember:
                    # add to whitelist, handle message again
                    self.user_whitelist.append(int(chat_id))
                    util.write_whitelist_to_file(self.user_whitelist[1:len(self.user_whitelist)])
                    self.handle(msg)
                    return
            # sender is not authorized to chat with bot
            self.logger.info(f"Unauthorized bot usage from {chat_id}")
            # Assemble reply
            reply_text = self.get_reply_text('no_Association')
            self.logger.info('would send not authorized')
            self.bot.sendMessage(chat_id, reply_text)
            
                
    def handle_callback_query(self, msg: dict):
        """handle callback queries - WORK IN PROGRESS

        Args:
            msg (dict): parsed from reply-json of each message to bot
        """

        query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')
        self.logger.info(f"Callback Query: {query_id}, {from_id}, {query_data}")
        if int(query_data) < 4: 
            ikm = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"blub{query_data}",callback_data='4')]])
            self.bot.editMessageReplyMarkup((from_id, self.messageID), reply_markup=ikm)
        else:
            self.bot.answerCallbackQuery(query_id, text='Got it')


    def start(self):
        """attach handle() and handle_callback_query() to bot - message_loop
        """
        self.bot.message_loop({'chat': self.handle, 'callback_query': self.handle_callback_query})
        self.logger.info("Bot started")

    
    def get_reply_text(self, kind: str, first_name: str = None):
        """Send approriate reply text

        Args:
            kind (str): which kind of reply, acts as switch value
            first_name (str, optional): for personalized messages, use first_name. Defaults to None.

        Returns:
            str:  a string containing the approriate reply
        """        

        reply = ''
        if kind == 'help':
            reply = f"Hi {first_name} - here are my available commands\n/edit_games: lets you edit your games\n/help: shows the list of available commands\n/stats: shows the status for our next game\n"

        elif kind == 'init':
            reply = f"Please try again by clicking on /start"

        elif kind == 'edit_games':
            reply = "Click on the game to change you attendance \\- in brackets you see your current status \\ \n*TIPP: the list ist scrollable*"

        elif kind == 'error':
            reply = "Hang on - an unknown error occured - please try again in a few minutes - Dominic has been informed"

        elif kind == 'hi':
            reply = f"Hi {first_name}"

        elif kind == 'no_Association':
            reply = f"You are not allowed to use this bot, if you think this is wrong doing, contact your referrer"

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


    def get_keyboard(self, kind: str, chat_id: int, button_list: list = None):
        """Get appropriate ReplyKeyboardMarkup

        Args:
            kind (str): which keyboard, acts as switch value
            chat_id (int): Telegram chat_id of the user the reply is sent to
            button_list (list, optional): [description]. Defaults to None.

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [telepot.ReplyKeyboardMarkup]: the assembled keyboard, None = no games in the future
        """        

        keyboard = None
        if kind == 'default':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/help', '/stats'], ['/edit_games']], resize_keyboard=True)
        elif kind == 'init':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/start']], resize_keyboard=True)
        elif kind == 'overview':
            try:
                buttons = self.database_handler.get_games_list_with_status(chat_id)
            except NotifyUserException as nuException:
                raise NotifyUserException(nuException)
            else:
                if len(buttons) < 2:
                    # there are no games in the future
                    return None
                keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
        elif kind == 'reminder_games':
            keyboard = ReplyKeyboardMarkup(keyboard=button_list, resize_keyboard=True)
        elif kind == 'remove':
            keyboard = ReplyKeyboardRemove()
        elif kind == 'select':
            keyboard = ReplyKeyboardMarkup(keyboard=[['YES', 'NO', 'UNSURE'], ['Overview', 'continue later']], resize_keyboard=True, one_time_keyboard=True)

        return keyboard


    def update_state_map(self, chat_id: int, new_state: int):
        """update the state map in program-dict and database

        Args:
            chat_id (int): chat_id of player_chat_i to change state
            new_state (int): new state to change to

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """        

        try: 
            # update DataBase
            self.database_handler.update_state(chat_id, new_state)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # update self.state_map
            self.state_map[chat_id] = new_state 


    def send_stats_to_group_chat(self):
        """send the current status to the group chat, if there is a game in exactly 4 days
        """
        player_list = self.database_handler.get_games_in_exactly_x_days(4)
        if len(player_list) >= 1:
            self.bot.sendMessage(self.group_chat_id, 'The stats for our next game are:\n' + self.get_reply_text('stats'), parse_mode= 'MarkdownV2')


def init_logger(config: configparser.RawConfigParser):
    """initialize the logger

    Args:
        config (configparser.RawConfigParser): the configuration file with which to initialize the Logger

    Returns:
        [logging.Logger]: the logger instance all modules have to use
    """    

    logger = logging.getLogger(__name__)
    # use a rotating file handler to save log at midnight
    logHandler = TimedRotatingFileHandler(filename="/home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_logger.log", when="midnight")
    formatter = logging.Formatter(fmt=config['Logging']["format"], datefmt='%d/%m/%Y %H:%M:%S')
    logHandler.setFormatter(formatter)
    logHandler.setLevel(config["Logging"]["level"])
    # add handler to logger
    logger.addHandler(logHandler)
    return logger


def main():
    """initialize:
    configuration parsing
    complete logger
    Bot
    """
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
        # run the scheduler_handler
        bot.scheduler_handler.run_schedule()
        time.sleep(10)


if __name__ == "__main__":
    main()


    """
    send inline button to handball.ch website
        self.bot.sendMessage(self.admin_chat_id, 'Handball.ch Website', reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                                   [InlineKeyboardButton(text="handball.ch/Züri West 1",url='https://www.handball.ch/de/matchcenter/teams/32010')]
                                ]
                            ))



    """
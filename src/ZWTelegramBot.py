import configparser
import datetime
import logging
import os
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler

import mariadb
import telepot
import utility as util
import ImportUtility as iUtil

from DatabaseHandler import DatabaseHandler
from PlayerState import PlayerState
from SpectatorState import SpectatorState
from StateObject import StateObject
from Scheduler import SchedulerHandler
from exceptions import NotifyUserException, NotifyAdminException
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, \
    InlineKeyboardButton


# static methods
def get_names(msg: dict):
    # Access first and last name, check if exists to avoid dict-key error
    last_name = ' No Name Given'
    first_name = ' No Name Given'
    if 'last_name' in msg['from'].keys():
        last_name = msg['from']['last_name'].capitalize()
    if 'first_name' in msg['from'].keys():
        first_name = msg['from']['first_name'].capitalize()
    return first_name, last_name


def init_database_handler(bot: telepot.Bot, db_config: configparser.RawConfigParser,
                          api_config: configparser.RawConfigParser, _logger: logging.Logger,
                          maintainer_chat_id: int):
    """initialize the DataBase Handler, retry 10 times on error, notify administrator otherwise and exit

    Args:
        bot (telepot.Bot): bot, used to notify the admin
        db_config (configparser.RawConfigParser):  provides the login credentials to the database
        api_config (configparser.RawConfigParser): provides the maintainer_chat_id
        _logger (logging.Logger): provides the logging facilities
        maintainer_chat_id (int): provide the maintainer_chat_id to the bot

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
                bot.sendMessage(maintainer_chat_id, f"ERROR: starting DB - BOT NOT RUNNING{err}")
                sys.exit(1)
        except NotifyAdminException as err:
            bot.sendMessage(maintainer_chat_id, f"ERROR: starting DB - BOT NOT RUNNING{err}")
        else:
            return database_handler


def init_admin_chat_ids(admin_chat_id: str):
    """load the admin_chat_ids saved in api_config to list for faster access

    Returns:
        list: A List containing all chat id's allowed to exchange admin-messages with the bot
    """
    admin_chat_list = []
    admin_chat_id_split = admin_chat_id.split(',')
    for admin_id in admin_chat_id_split:
        admin_chat_list.append(int(admin_id))
    return admin_chat_list


class ZWTelegramBot(object):

    def __init__(self, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser,
                 db_config: configparser.RawConfigParser, _logger: logging.Logger):
        """initialize main class with bot, start all Handlers

        Args:
            config (configparser.RawConfigParser): configuration file for bot
            api_config (configparser.RawConfigParser): configuration file with secrets (Bot Token, maintainer_chat_id)
            db_config (configparser.RawConfigParser): configuration file for database handler
            _logger (logging.Logger): logger instance, will be passed to databaseHandler and scheduleHandler
            -> one logger for all classes
        """

        # initialize fields
        self.config = config
        self.api_config = api_config
        self.maintainer_chat_id = int(self.api_config["API"]["maintainer_chat_id"])
        self.group_chat_id = int(self.api_config["API"]["group_chat_id"])
        self.group_chat_id2 = int(self.api_config["API"]["group_chat_id2"])
        self.admin_chat_ids = init_admin_chat_ids(self.api_config["API"]["admin_chat_ids"])
        self.add_infos_dict = dict()  # dict from chat_id to list: [dateTime, Place, Opponent]

        # initialize logger 
        self.logger = _logger
        self.logger.info("start main\n\n")
        self.logger.info("Logger started")

        # start Bot
        self.bot = telepot.Bot(self.api_config["API"]["key"])

        # start DataBase Handler
        self.database_handler = init_database_handler(self.bot, db_config, api_config, _logger,
                                                      self.maintainer_chat_id)

        # initialize lists / dicts
        self.user_state_map = self.database_handler.init_user_state_map()
        self.spectator_state_map = self.database_handler.init_spectator_state_map()

        # start Scheduler Handler
        self.scheduler_handler = SchedulerHandler(api_config, self.bot, self.database_handler, _logger)
        # self.scheduler_handler.send_reminder_at_8am(self.send_reminders)
        # self.scheduler_handler.send_stats_to_group_chat(self.send_stats_to_group_chat)

        # adding games manually via ics, to delete
        # path = os.path.join('ics', 'someFile.ics')
        # sql_statements = iUtil.parse_file(path)
        # for sql_stat in sql_statements:
        #     self.database_handler.execute_mysql_without_result(sql_stat, 0)


        # testing - TO DELETE
        # info = self.bot.sendMessage(self.maintainer_chat_id, 'testing custom keyboard',
        #                               reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        #                                   [InlineKeyboardButton(text="One",callback_data='1'),
        #                                   InlineKeyboardButton(text="Two",callback_data='2'),
        #                                   InlineKeyboardButton(text="Three",callback_data='3')],
        #                        ]
        #                   ))
        # self.messageID = info['message_id']

    def send_reminders(self):
        """send reminders to all unsure players for games in 5/6/7/12 days
        """
        try:
            # get all unsure players and their respective games (they are unsure at)
            player_to_messages_map = self.scheduler_handler.load_schedules()
        except NotifyAdminException as err:
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"loading schedules did not succeed - no scheduled messages today\n{err}")
        else:
            # loop through all pairs of players and game-strings
            for player_chat_id, games in player_to_messages_map.items():
                # assemble reminder text
                reminder_text = "Hey, we still need to know whether you will play in the following games:\n"
                button_list = [['continue later']]
                for game in games:
                    # add each pretty-printed game to reminder_text and button list
                    game_info = f"{util.make_datetime_pretty_str(game[0])} | {game[2]}"
                    reminder_text += f"{game_info}\n"
                    button_list.append([game_info])
                # assemble bot-reply (custom keyboard containing all games to still edit)
                reply_keyboard = self.get_keyboard('reminder_games', -1, button_list=button_list)
                self.bot.sendMessage(player_chat_id, reminder_text, reply_markup=reply_keyboard)
                self.update_state_map(player_chat_id, 0)

    def handle(self, msg: dict):
        """Called each time a message is sent to the bot

        Args:
            msg (dict): parsed from reply-json of each message to bot
        """

        content_type, chat_type, chat_id = telepot.glance(msg)
        self.logger.info(msg)
        # private chat reply
        if chat_type == 'private':
            first_name, last_name = get_names(msg)
            # check if user in self.user_state_map / authorized to use bot
            if chat_id in self.user_state_map.keys():

                # chat_id allowed to use admin-commands:
                is_admin = chat_id in self.admin_chat_ids

                try:
                    if content_type == 'text':

                        command = msg['text'].lower()

                        self.logger.info(f"Got command: {command} from {chat_id}")

                        current_state = (self.user_state_map[chat_id]).state
                        # Switch for state of current user
                        if current_state is PlayerState.INIT:

                            if command == '/start':
                                # add player_chat_id to Database if not already added
                                if not self.database_handler.player_present(chat_id):
                                    self.database_handler.insert_new_player(chat_id, first_name, last_name)
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # send reply
                                    reply_text = self.get_reply_text('start')
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            else:
                                reply_text = self.get_reply_text('init')
                                reply_keyboard = self.get_keyboard('init', chat_id)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            return

                        elif current_state is PlayerState.DEFAULT:
                            # handle default
                            if is_admin:
                                if command == '/add':
                                    self.logger.info('got /add')
                                    reply_text = self.get_reply_text('add', first_name)
                                    reply_keyboard = self.get_keyboard('add', chat_id)
                                    self.update_user_state_map(chat_id, PlayerState.ADD)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    return
                                elif command == '/spectators':
                                    self.update_user_state_map(chat_id, PlayerState.SPECTATOR_CHOOSE_PENDING)
                                    reply_text = self.get_reply_text('choose_pending_spectator', first_name)
                                    button_list = self.database_handler.get_pending_spectators()
                                    reply_keyboard = self.get_keyboard('pending_spectators', chat_id,
                                                                       button_list=button_list)
                                    if reply_keyboard is None or button_list is None:
                                        # there are no games in the future, reset State
                                        self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                        # Assemble reply
                                        reply_text = self.get_reply_text('no_pending_spectators', first_name)
                                        reply_keyboard = self.get_keyboard('default', first_name, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    return
                                elif command == '/get_player_stats':
                                    reply_text = self.get_reply_text('player_stats', first_name, is_admin=is_admin)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    reply_text = self.get_reply_text('get_playerState_Enum', first_name,
                                                                     is_admin=is_admin)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    return
                            if command == '/help':
                                reply_text = self.get_reply_text('help', first_name, is_admin=is_admin)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                return
                            elif command == '/edit_games':
                                self.update_user_state_map(chat_id, PlayerState.EDIT_CHOOSE_GAME)
                                reply_text = self.get_reply_text('edit_games', first_name)
                                reply_keyboard = self.get_keyboard('overview_edit_games', chat_id)
                                if reply_keyboard is None:
                                    # there are no games in the future, reset State
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('overview_no_games', first_name)
                                    reply_keyboard = self.get_keyboard('default', first_name, is_admin=is_admin)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                     parse_mode='MarkdownV2')
                                return
                            elif command == '/start':
                                reply_text = self.get_reply_text('start', first_name)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                return
                            elif command == '/stats':
                                self.update_user_state_map(chat_id, PlayerState.GET_STATS)
                                reply_text = self.get_reply_text('stats_overview', first_name)
                                reply_keyboard = self.get_keyboard('overview_stats', chat_id)
                                if reply_keyboard is None:
                                    # no games in the future
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    reply_text = self.get_reply_text('overview_no_games', first_name)
                                    reply_keyboard = self.get_keyboard('default', first_name, is_admin=is_admin)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                     parse_mode='MarkdownV2')
                                return
                            elif command == '/website':
                                # send inline button to handball.ch website
                                reply_text = self.get_reply_text('website', first_name)
                                reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                                    text="handball.ch/Züri West 1",
                                    url='https://www.handball.ch/de/matchcenter/teams/36769')]])
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                return
                            else:
                                self.handle_else(msg, chat_id)
                                return

                        elif current_state is PlayerState.GET_STATS:
                            # handle getStats
                            if command == 'continue later':
                                self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                # Assemble reply
                                reply_text = self.get_reply_text('continue later', first_name)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            else:
                                game_date = command[:18]
                                current_game_id = self.database_handler.get_game_id(game_date)
                                if current_game_id >= 0:
                                    self.user_state_map[chat_id].game_number = current_game_id
                                    # assemble reply with select-keyboard
                                    reply_text = self.get_reply_text('stats',
                                                                     game_id=self.user_state_map[chat_id].game_number)
                                    reply_keyboard = self.get_keyboard('overview_stats', chat_id)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                         parse_mode='MarkdownV2')
                                else:
                                    # Game not in DataBase, ignore input
                                    self.logger.warning(f"Game not found, got {command}")
                                    self.handle_else(msg, chat_id)

                        elif current_state.name.startswith('ADD'):
                            self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                        #     # handle ADD cases
                        #     if current_state is PlayerState.ADD:
                        #         # handle ADD
                        #     elif current_state.name.startswith('ADD_HB'):
                        #         if current_state is PlayerState.ADD_HB_1:
                        #             # handle
                        #         elif current_state is PlayerState.ADD_HB_2:
                        #             # handle
                        #         elif current_state is PlayerState.ADD_HB_3:
                        #             #handle
                        #     elif current_state.name.startswith('ADD_TK'):
                        #         if current_state is PlayerState.ADD_TK_1:
                        #             # handle
                        #         elif current_state is PlayerState.ADD_TK_2:
                        #             # handle
                        #         elif current_state is PlayerState.ADD_TK_3:
                        #             #handle
                        #     elif current_state is PlayerState.ADD_CONFIRM:
                        #         # handle
                        #     else:
                        #         # handle default???

                        elif current_state.name.startswith('EDIT'):
                            self.logger.info(f"in edit games, STATE startswith(EDIT)")
                            if current_state is PlayerState.EDIT_CHOOSE_GAME:
                                if command == 'continue later':
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                else:
                                    game_date = command[:18]
                                    current_game_id = self.database_handler.get_game_id(game_date)
                                    if current_game_id >= 0:
                                        self.update_user_state_map(chat_id, PlayerState.EDIT_GAME)
                                        self.user_state_map[chat_id].game_number = current_game_id
                                        # assemble reply with select-keyboard
                                        reply_text = self.get_reply_text('selection', first_name)
                                        reply_keyboard = self.get_keyboard('select', chat_id)
                                        self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                    else:
                                        # Game not in DataBase, ignore input
                                        self.logger.warning(f"in Edit-else: Game not found, got {command}")
                                        reply_text = self.get_reply_text('edit_games', first_name, mnu=True)
                                        reply_keyboard = self.get_keyboard('overview_edit_games', chat_id)
                                        if reply_keyboard is None:
                                            # no games in the future
                                            self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                            reply_text = self.get_reply_text('overview_no_games', first_name)
                                            reply_keyboard = self.get_keyboard('default', first_name, is_admin=is_admin)
                                        self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                             parse_mode='MarkdownV2')

                            elif current_state is PlayerState.EDIT_GAME:
                                if util.status_is_valid(command):
                                    self.database_handler.edit_game_attendance(self.user_state_map[chat_id].game_number,
                                                                               command, chat_id)
                                    # send overview again
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    msg['text'] = '/edit_games'
                                    self.handle(msg)
                                elif command == 'overview':
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    msg['text'] = '/edit_games'
                                    self.handle(msg)
                                elif command == 'continue later':
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                else:
                                    self.handle_else(msg, chat_id)

                        elif current_state.name.startswith('SPECTATOR'):
                            if current_state is PlayerState.SPECTATOR_CHOOSE_PENDING:
                                split = command.split('|')
                                if len(split) > 1:
                                    (self.user_state_map[chat_id]).spectator_id = int(split[0].strip())
                                    reply_text = self.get_reply_text('spectator_app_or_ref', split[1])
                                    reply_keyboard = self.get_keyboard('app_or_ref', chat_id)
                                    self.update_user_state_map(chat_id, PlayerState.SPECTATOR_APP_OR_REF)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                                elif command == 'continue later':
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                            elif current_state is PlayerState.SPECTATOR_APP_OR_REF:
                                if command in ['approve', 'refuse']:
                                    new_spectator_state = SpectatorState.REFUSED
                                    spectator_chat_id = (self.user_state_map[chat_id]).spectator_id
                                    reply_text = self.get_reply_text('spectator_refused')
                                    if command == 'approve':
                                        new_spectator_state = SpectatorState.DEFAULT
                                        spec_reply_text = self.get_reply_text('spectator_approved', is_spectator=True)
                                        spec_reply_text += '\n' + self.get_reply_text('help', first_name='',
                                                                                      is_spectator=True)
                                        # notify spectator
                                        spec_reply_keyboard = self.get_keyboard('help', spectator_chat_id,
                                                                                is_spectator=True)
                                        self.bot.sendMessage(spectator_chat_id, spec_reply_text,
                                                             reply_markup=spec_reply_keyboard)
                                        reply_text = self.get_reply_text('spectator_approved')
                                    else:
                                        spec_reply_text = self.get_reply_text('spectator_refused', is_spectator=True)
                                        self.bot.sendMessage(spectator_chat_id, spec_reply_text)

                                    self.database_handler.update_spectator_state(spectator_chat_id, new_spectator_state)
                                    self.update_spectator_state_map(spectator_chat_id, new_spectator_state)

                                    # reply to chat_id
                                    self.bot.sendMessage(chat_id, reply_text)
                                    # rehandle message
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    msg['text'] = '/spectators'
                                    self.handle(msg)

                                elif command == 'continue later':
                                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                                    # Assemble reply
                                    reply_text = self.get_reply_text('continue later', first_name)
                                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

                        else:
                            # user in no valid state, reset, notify admin
                            self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                            reply_text = f"User ({chat_id}) in no valid state: {current_state}"
                            self.bot.sendMessage(self.maintainer_chat_id, reply_text)
                            raise NotifyUserException

                    # got something different from text, ignore
                    else:
                        self.logger.info(f"Got {content_type} from {chat_id}")

                except NotifyUserException as nuException:
                    # something went wrong
                    self.update_user_state_map(chat_id, PlayerState.DEFAULT)
                    # send error to admin
                    self.bot.sendMessage(self.maintainer_chat_id,
                                         f"Error in executing the following query:\n{nuException}")
                    # Assemble reply, notify user an error occurred
                    reply_text = self.get_reply_text('error', first_name)
                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=is_admin)
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

            elif chat_id in self.spectator_state_map.keys():
                try:
                    if content_type == 'text':

                        command = msg['text'].lower()

                        self.logger.info(f"Got command: {command} from {chat_id}")

                        current_state = self.spectator_state_map[chat_id]
                        # Switch for state of current user
                        if current_state is SpectatorState.AWAIT_APPROVE:
                            reply_text = self.get_reply_text('await_approve')
                            self.bot.sendMessage(chat_id, reply_text)
                        elif current_state is SpectatorState.REFUSED:
                            # just ignore
                            return
                        elif current_state is SpectatorState.DEFAULT:
                            if command == '/help':
                                # Assemble reply
                                reply_text = self.get_reply_text('help', first_name, is_spectator=True)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_spectator=True)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            elif command == '/start':
                                # Assemble reply
                                reply_text = self.get_reply_text('start', first_name, is_spectator=True)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_spectator=True)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            elif command == '/games':
                                # Assemble reply
                                self.update_spectator_state_map(chat_id, SpectatorState.CHOOSE_GAME)
                                reply_text = self.get_reply_text('stats_overview', first_name, is_spectator=True)
                                reply_keyboard = self.get_keyboard('overview_stats', chat_id, is_spectator=True)
                                if reply_keyboard is None:
                                    # no games in the future
                                    self.update_spectator_state_map(chat_id, SpectatorState.DEFAULT)
                                    reply_text = self.get_reply_text('overview_no_games', first_name)
                                    reply_keyboard = self.get_keyboard('default', first_name, is_spectator=True)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                     parse_mode='MarkdownV2')
                            elif command == '/website':
                                # send inline button to handball.ch website
                                reply_text = self.get_reply_text('website', first_name)
                                reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                                    text="handball.ch/Züri West 1",
                                    url='https://www.handball.ch/de/matchcenter/teams/34393')]])
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            else:
                                self.handle_else(msg, chat_id, is_spectator=True)
                        elif current_state is SpectatorState.CHOOSE_GAME:
                            if command == 'continue later':
                                self.update_spectator_state_map(chat_id, SpectatorState.DEFAULT)
                                # Assemble reply
                                reply_text = self.get_reply_text('continue later', first_name)
                                reply_keyboard = self.get_keyboard('default', chat_id, is_spectator=True)
                                self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)
                            else:
                                game_date = command[:18]
                                current_game_id = self.database_handler.get_game_id(game_date)
                                if current_game_id >= 0:
                                    # assemble reply with select-keyboard
                                    reply_text = self.get_reply_text('stats', game_id=current_game_id)
                                    reply_keyboard = self.get_keyboard('overview_stats', chat_id, is_spectator=True)
                                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard,
                                                         parse_mode='MarkdownV2')
                                else:
                                    # Game not in DataBase, ignore input
                                    self.logger.warning(f"Game not found, got {command}")
                                    self.handle_else(msg, chat_id)
                        else:
                            # handle
                            pass
                except NotifyUserException as nuException:
                    # something went wrong
                    self.update_spectator_state_map(chat_id, SpectatorState.DEFAULT)
                    # send error to admin
                    self.bot.sendMessage(self.maintainer_chat_id,
                                         f"Error in executing the following query:\n{nuException}")
                    # Assemble reply, notify user an error occurred
                    reply_text = self.get_reply_text('error', first_name)
                    reply_keyboard = self.get_keyboard('default', chat_id, is_spectator=True)
                    self.bot.sendMessage(chat_id, reply_text, reply_markup=reply_keyboard)

            else:
                # message from user, check if in group
                chat_member_information = self.bot.getChatMember(self.group_chat_id, chat_id)
                status_information = chat_member_information['status']
                is_member = bool(util.is_member_of_group(status_information))
                if is_member:
                    # add to whitelist, handle message again
                    self.user_state_map[int(chat_id)] = StateObject(PlayerState.INIT)
                    self.handle(msg)
                    return
                else:
                    self.update_spectator_state_map(chat_id, SpectatorState.AWAIT_APPROVE, firstname=first_name,
                                                    lastname=last_name)
                    self.logger.info('new usage, wait for approve')
                    # Notify maintainer
                    reply_text = self.get_reply_text('new_spectator')
                    reply_keyboard = self.get_keyboard('default', chat_id, is_admin=True)
                    self.bot.sendMessage(self.maintainer_chat_id, reply_text, reply_markup=reply_keyboard)
                    # notify user
                    self.handle(msg)

        # group chat reply
        elif chat_type in ['group', 'supergroup']:

            if chat_id == self.group_chat_id:
                try:
                    if content_type == 'text':
                        command = msg['text']
                        self.logger.info(f"Group-Message - Got {command} from {chat_id}")

                        if command.startswith('@Zuri_West_Manager_Bot'):
                            # directly addressed at the bot, answer
                            command = command[23:]
                            if 'stats' in command:
                                self.bot.sendMessage(chat_id,
                                                     'The stats for our next game are:\n' + self.get_reply_text(
                                                         'stats'), parse_mode='MarkdownV2')

                    else:
                        self.logger.info(f"Got {content_type} from Group-chat ({chat_id})")

                except (NotifyUserException, NotifyAdminException) as nuException:
                    self.bot.sendMessage(self.maintainer_chat_id,
                                         f"Error in executing the following query:\n{nuException}")
            else:
                # bot added to group chat
                self.bot.sendMessage(self.maintainer_chat_id,
                                     f"Unauthorized usage from group chat: {chat_id}")

        elif chat_type == 'channel':
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"bot added to channel: {chat_id}")

        else:
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"unknown chat_type {chat_type}")

    def handle_else(self, msg: dict, chat_id: int, is_spectator: bool = False):
        self.logger.info(f"handle_else, got {msg} from {chat_id}")
        # chat is private and text
        first_name, last_name = get_names(msg)
        command = msg['text'].lower()
        if command == '/hi' or command == 'hi':
            # Assemble reply
            reply_text = self.get_reply_text('hi', first_name)
            self.bot.sendMessage(chat_id, reply_text)
        else:
            if is_spectator:
                # send /help after updating to default
                self.update_spectator_state_map(chat_id, SpectatorState.DEFAULT)
            else:
                # send /help after updating to default
                self.update_user_state_map(chat_id, PlayerState.DEFAULT)
            msg['text'] = '/help'
            self.handle(msg)

    def handle_callback_query(self, msg: dict):
        """handle callback queries - WORK IN PROGRESS

        Args:
            msg (dict): parsed from reply-json of each message to bot
        """

        query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')
        self.logger.info(f"Callback Query: {query_id}, {from_id}, {query_data}")
        if int(query_data) < 4:
            ikm = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=f"blurb{query_data}", callback_data='4')]])
            self.bot.editMessageReplyMarkup((from_id, self.messageID), reply_markup=ikm)
        else:
            self.bot.answerCallbackQuery(query_id, text='Got it')

    def start(self):
        """attach handle() and handle_callback_query() to bot - message_loop
        """
        self.bot.message_loop({'chat': self.handle, 'callback_query': self.handle_callback_query})
        self.logger.info("Bot started")

    def get_reply_text(self, kind: str, first_name: str = None, is_admin: bool = False, game_id: int = -1,
                       is_spectator: bool = False, mnu: bool = False):
        """Send appropriate reply text

        Args:
            mnu (bool): MessageNotUnderstood: prepends the MNU message
            is_spectator: is the user a spectator or normal player
            game_id: the game id to get the status to
            kind (str): which kind of reply, acts as switch value
            first_name (str, optional): for personalized messages, use first_name. Defaults to None.
            is_admin (bool, optional): is the person admin? (more possible commands)

        Returns:
            str:  a string containing the appropriate reply
        """

        reply = ''
        if kind == 'add':
            reply = f"Let's add a new event: is it a Handball-Game or a Timekeeper-Event?" \
                    f"\nYou can write /cancel to " \
                    f"cancel the process any time."

        elif kind == 'await_approve':
            reply = f"Wait for the administrator to approve your status as spectator\\."

        elif kind == 'choose_pending_spectator':
            reply = f"Choose the pending spectator to approve or refuse\\."

        elif kind == 'help':
            if is_admin:
                reply = f"Hi {first_name} - here are my available commands" \
                        f"\n/edit_games: lets you edit your games" \
                        f"\n/help: shows the list of available commands" \
                        f"\n/stats: shows the status for our next game" \
                        f"\n/add: add new game or Timekeeper event" \
                        f"\n/website: Returns the link for Handball.ch/Züri West" \
                        f"\n/spectators: show the list of currently (pending) spectators of the bot" \
                        f"\n/get_player_stats: dump the contents of the Players table"
            elif is_spectator:
                reply = f"Hi {first_name} - here are my available commands" \
                        f"\n/help: shows the list of available commands" \
                        f"\n/games: shows the status for our next games" \
                        f"\n/website: Returns the link for Handball.ch/Züri West"
            else:
                reply = f"Hi {first_name} - here are my available commands" \
                        f"\n/edit_games: lets you edit your games" \
                        f"\n/help: shows the list of available commands" \
                        f"\n/stats: shows the status for our next games" \
                        f"\n/website: Returns the link for Handball.ch/Züri West"

        elif kind == 'init':
            reply = f"Please try again by clicking on /start\\!"

        elif kind == 'edit_games':
            reply = "Click on the game to change you attendance \\- in brackets you see your current status \\ " \
                    "\n*TIPP: the list is scrollable\\!*"

        elif kind == 'error':
            reply = "Hang on - an unknown error occurred - please try again in a few minutes - " \
                    "Dominic has been informed\\."

        elif kind == 'get_playerState_Enum':
            reply = util.pretty_print_player_states()

        elif kind == 'hi':
            reply = f"Hi {first_name}"

        elif kind == 'new_spectator':
            reply = f"New spectator to approve available\\. Access via /spectators"

        elif kind == 'no_Association':
            reply = f"You are not allowed to use this bot, if you think this is wrong doing, contact your referrer\\!"

        elif kind == 'no_pending_spectators':
            reply = f"There are no pending spectators\\!"

        elif kind == 'overview_no_games':
            reply = 'There are no upcoming games\\!'

        elif kind == 'opponent':
            reply = f"Great, against whom will we play?" \
                    f"\n(write /cancel to cancel the process)"

        elif kind == 'player_stats':
            reply = self.database_handler.get_player_stats()

        elif kind == 'spectator_app_or_ref':
            reply = f"Do you want to approve or refuse {first_name}?"

        elif kind == 'spectator_approved':
            if is_spectator:
                reply = 'You have been approved\\!'
            else:
                reply = f"You approved the spectator\\!"

        elif kind == 'spectator_refused':
            if is_spectator:
                reply = 'You have been refused. If you think this is wrong, contact the administrator\\.'
            else:
                reply = "You refused the spectator\\!"

        elif kind == 'start':
            if is_spectator:
                reply = f"Hi {first_name}! \nI am the Züri West Manager " \
                        f"\nBelow you see the available commands "
            else:
                reply = f"Hi {first_name}! \nI am the Züri West Manager " \
                        f"\nBelow you see the available commands " \
                        f"\nWhen your are ready, click on \'/edit_games\' to mark your presence in Züri West handball games"

        elif kind == 'stats_overview':
            if is_spectator:
                reply = "Click on the game to get the stats for" \
                        "\n*TIPP: the list is scrollable*"
            else:
                reply = "Click on the game to get the stats for \\- the summary is of the format: " \
                        "\n 5 *Y*ES \\- 3 *N*O \\- 4 *U*NSURE " \
                        "\n*TIPP: the list is scrollable*"

        elif kind == 'stats':
            reply = self.database_handler.get_stats_game(game_id)

        elif kind == 'continue later':
            reply = f"Cheerio, {first_name}"

        elif kind == 'selection':
            reply = 'Will you be there (YES), be absent (NO) or are not sure yet (UNSURE)?'

        elif kind == 'website':
            reply = 'Here it is:'

        elif kind == 'when':
            reply = 'Please indicate WHEN the event will take place' \
                    '\nDo this in the following format:' \
                    '\n01.01.2020 20:30' \
                    '\n(write /cancel to cancel the process)'

        elif kind == 'when_fail':
            reply = 'Try again, the format did not match.' \
                    '\nTry the following format:' \
                    '\n01.01.2020 20:30' \
                    '\n(write /cancel to cancel the process)'

        elif kind == 'where':
            reply = 'Fantastic, WHERE will the event be?' \
                    '\n(write /cancel to cancel the process)'
        if mnu:
            mnu = "Sorry\\, I didn't understand that\\. Maybe there is a typo in your response\\?\n\n"
            return mnu + reply
        return reply

    def get_keyboard(self, kind: str, chat_id: int, button_list: list = None, is_admin: bool = False,
                     is_spectator: bool = False):
        """Get appropriate ReplyKeyboardMarkup

        Args:
            is_spectator (bool) : is the user a spectator or normal player
            kind (str): which keyboard, acts as switch value
            chat_id (int): Telegram chat_id of the user the reply is sent to
            button_list (list, optional): [description]. Defaults to None.
            is_admin (bool, optional): is the person admin? (more possible commands)

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [telepot.ReplyKeyboardMarkup]: the assembled keyboard, None = no games in the future
        """

        keyboard = None
        if kind == 'add':
            keyboard = ReplyKeyboardMarkup(keyboard=[['Handball Game'], ['Timekeeper Event']],
                                           resize_keyboard=True)
        elif kind == 'app_or_ref':
            keyboard = ReplyKeyboardMarkup(keyboard=[['Approve', 'Refuse'], ['continue later']],
                                           resize_keyboard=True)
        elif kind == 'default':
            if is_admin:
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[['/help', '/stats', '/edit_games'], ['/spectators', '/add', '/website'],
                              ['/get_player_stats']],
                    resize_keyboard=True)
            elif is_spectator:
                keyboard = ReplyKeyboardMarkup(keyboard=[['/help', '/website'], ['/games']],
                                               resize_keyboard=True)
            else:
                keyboard = ReplyKeyboardMarkup(keyboard=[['/help', '/stats'], ['/edit_games', '/website']],
                                               resize_keyboard=True)
        elif kind == 'init':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/start']], resize_keyboard=True)

        elif kind == 'ok_or_cancel':
            keyboard = ReplyKeyboardMarkup(keyboard=[['/ok', '/cancel']], resize_keyboard=True)
        elif kind.startswith('overview_'):
            try:
                buttons = [['']]
                if kind == 'overview_edit_games':
                    buttons = self.database_handler.get_games_list_with_status(chat_id)
                elif kind == 'overview_stats':
                    if is_spectator:
                        buttons = self.database_handler.get_games_list_for_spectator()
                    else:
                        buttons = self.database_handler.get_games_list_with_status_summary()
            except NotifyUserException as nuException:
                raise NotifyUserException(nuException)
            else:
                if len(buttons) < 2:
                    # there are no games in the future
                    return None
                keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
        elif kind == 'pending_spectators':
            keyboard = ReplyKeyboardMarkup(keyboard=button_list, resize_keyboard=True)
        elif kind == 'reminder_games':
            keyboard = ReplyKeyboardMarkup(keyboard=button_list, resize_keyboard=True)
        elif kind == 'remove':
            keyboard = ReplyKeyboardRemove()
        elif kind == 'select':
            keyboard = ReplyKeyboardMarkup(keyboard=[['YES', 'NO', 'UNSURE'], ['Overview', 'continue later']],
                                           resize_keyboard=True, one_time_keyboard=True)
        elif keyboard == 'website':
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="handball.ch/Züri West 1",
                                                       url='https://www.handball.ch/de/matchcenter/teams/32010')]])
        return keyboard

    def update_user_state_map(self, chat_id: int, new_state: PlayerState):
        """update the state map in program-dict and database

        Args:
            chat_id (int): chat_id of player_chat_i to change state
            new_state (PlayerState): new state to change to

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """

        self.logger.info(f"updating User state for {chat_id} from {self.user_state_map[chat_id].state} to {new_state}")
        try:
            # update DataBase
            self.database_handler.update_player_state(chat_id, new_state)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # update self.state_map
            self.user_state_map[chat_id].state = new_state
            if new_state is not PlayerState.EDIT_GAME:
                self.user_state_map[chat_id].game_number = -1
            if new_state is not PlayerState.SPECTATOR_APP_OR_REF:
                self.user_state_map[chat_id].spectator_id = -1

    def update_spectator_state_map(self, chat_id: int, new_state: SpectatorState, firstname: str = '',
                                   lastname: str = ''):
        """update the state map in program-dict and database

        Args:
            lastname: ...
            firstname: ...
            chat_id (int): chat_id of player_chat_i to change state
            new_state (SpectatorState): new state to change to

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """
        self.logger.info(
            f"updating spectator state for {chat_id} from {self.spectator_state_map[chat_id]} to {new_state}")
        try:
            # update DataBase
            if chat_id in self.spectator_state_map.keys():
                self.database_handler.update_spectator_state(chat_id, new_state)
            else:
                self.database_handler.add_spectator(chat_id, firstname, lastname)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # update self.state_map
            self.spectator_state_map[chat_id] = new_state

    def send_stats_to_group_chat(self):
        """send the current status to the group chat, if there is a game in exactly 4 days
        """
        player_list = self.database_handler.get_games_in_exactly_x_days(4)
        if len(player_list) >= 1:
            self.bot.sendMessage(self.group_chat_id,
                                 'The stats for our next game are:\n' + self.get_reply_text('stats'),
                                 parse_mode='MarkdownV2')


def init_logger(config: configparser.RawConfigParser):
    """initialize the logger

    Args:
        config (configparser.RawConfigParser): the configuration file with which to initialize the Logger

    Returns:
        [logging.Logger]: the logger instance all modules have to use
    """

    logger = logging.getLogger(__name__)
    # use a rotating file handler to save log at midnight
    log_handler = TimedRotatingFileHandler(filename="/home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_logger.log",
                                           when="midnight")
    formatter = logging.Formatter(fmt=config['Logging']["format"], datefmt='%d/%m/%Y %H:%M:%S')
    log_handler.setFormatter(formatter)
    log_handler.setLevel(config["Logging"]["level"])
    # add handler to logger
    logger.addHandler(log_handler)
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

    zw_logger = init_logger(config)

    # Logging
    logging_arguments = dict()
    logging_arguments["format"] = config['Logging']["format"]
    logging_arguments["level"] = logging.getLevelName(
        config["Logging"]["level"])
    if config["Logging"].getboolean("to_file"):
        logging_arguments["filename"] = config["Logging"]['logfile']
    logging.basicConfig(**logging_arguments)

    # Start botting
    bot = ZWTelegramBot(config, api_config, db_config, zw_logger)
    bot.start()

    while True:
        # run the scheduler_handler
        bot.scheduler_handler.run_schedule()
        time.sleep(10)


if __name__ == "__main__":
    main()

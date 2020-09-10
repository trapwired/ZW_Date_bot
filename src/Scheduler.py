import schedule
import time
import telepot
import functools
import logging
import configparser

from datetime import date

from DatabaseHandler import DatabaseHandler
from exceptions import NotifyAdminException, NotifyUserException


class SchedulerHandler(object):

    def __init__(self, config: configparser.RawConfigParser, bot: telepot.Bot, db_handler: DatabaseHandler, _logger: logging.Logger):
        """initialize the scheduler Handler

        Args:
            config (configparser.RawConfigParser): configuration file to get group and admin chat_id
            bot (telepot.Bot): main bot, used to send messages to admin in case of error
            db_handler (DatabaseHandler): DataBase Handler-instance
            _logger (logging.Logger): logger instance, the same over all modules, log to same file
        """

        # initialize fields
        self.bot = bot
        self.group_id = config['API']['group_chat_id']
        self.admin_chat_id = config['API']['admin_chat_id']
        self.database_handler = db_handler
        self.logger = _logger

        # since server restarts every 24hours, send error to admin if more than 24 hours up
        schedule.every(24).hours.do(self.send_reboot_failure)

        # init complete
        self.logger.info('Scheduler Handler started')


    def send_reboot_failure(self):
        """send a message to the admin that reboot has failed
        """
        self.bot.sendMessage(self.admin_chat_id, 'ERROR - Bot restart failed)')


    def load_schedules(self):
        """Iterates through all Games in 5/6/7/14 days and returns a list of chat_ids of players that indicated UNSURE in any of the Games

        Returns:
            dict(): a dictionary from chat_ids to lists of game infos ([game_date, game_place, game_adversary])
        """
        try:
            # get the games_lists
            five_days_games_list = self.database_handler.get_games_in_exactly_x_days(4)
            six_days_games_list = self.database_handler.get_games_in_exactly_x_days(5)
            seven_days_games_list = self.database_handler.get_games_in_exactly_x_days(6)
            fourteen_days_games_list = self.database_handler.get_games_in_exactly_x_days(13)

            player_to_messages_map = dict()
        except NotifyAdminException:
            self.bot.sendMessage(self.admin_chat_id, 'Getting the 5 days game did not work, no schedules set for today')
        else:
            # loop over games_lists, append all unsure players to player_to_messages_map
            for (game_info_list, unsure_players_list) in five_days_games_list:
                for unsure_player in unsure_players_list:
                    if unsure_player not in player_to_messages_map:
                        player_to_messages_map[unsure_player] = []
                    player_to_messages_map[unsure_player].append(game_info_list)
            for (game_info_list, unsure_players_list) in six_days_games_list:
                for unsure_player in unsure_players_list:
                    if unsure_player not in player_to_messages_map:
                        player_to_messages_map[unsure_player] = []
                    player_to_messages_map[unsure_player].append(game_info_list)
            for (game_info_list, unsure_players_list) in seven_days_games_list:
                for unsure_player in unsure_players_list:
                    if unsure_player not in player_to_messages_map:
                        player_to_messages_map[unsure_player] = []
                    player_to_messages_map[unsure_player].append(game_info_list)
            for (game_info_list, unsure_players_list) in fourteen_days_games_list:
                for unsure_player in unsure_players_list:
                    if unsure_player not in player_to_messages_map:
                        player_to_messages_map[unsure_player] = []
                    player_to_messages_map[unsure_player].append(game_info_list)
            return player_to_messages_map
 

    def send_reminder_at_8am(self, function):
        """schedule function at 8am

        Args:
            function (function): function to be scheduled at 8am
        """
        schedule.every().day.at("08:00").do(function)
    

    def send_stats_to_group_chat(self, function):
        """schedule function at 10pm

        Args:
            function (function): function to be scheduled at 10pm
        """
        schedule.every().day.at("22:00").do(function)


    def run_schedule(self):
        """function looped in ZWTelegramBot to run scheduled jobs
        """
        schedule.run_pending()

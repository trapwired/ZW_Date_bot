import schedule
import time
import telepot
import functools
import logging
from datetime import date

from DatabaseHandler import DatabaseHandler
from exceptions import NotifyAdminException, NotifyUserException


class SchedulerHandler(object):

    def __init__(self, config, bot: telepot.Bot, db_handler: DatabaseHandler, _logger: logging.Logger):
        self.bot = bot
        self.group_id = config['API']['group_chat_id']
        self.admin_chat_id = config['API']['admin_chat_id']
        self.database_handler = db_handler
        self.logger = _logger

        # since server restarts every 24hours, send error to admin if more than 24 hours up
        schedule.every(24).hours.do(self.send_reboot_failure)

        self.logger.info('Scheduler Handler started')


    def send_reboot_failure(self):
        self.bot.sendMessage(self.admin_chat_id, 'ERROR - Bot restart failed)')


    def load_schedules(self):
        """Iterates through all Games in 5/6/7/14 days and returns a list of chat_ids of players that indicated UNSURE in any of the Games

        Returns:
            dict(): a dictionary from chat_ids to lists of game infos ([game_date, game_place, game_adversary])
        """
        try:
            five_days_games_list = self.database_handler.get_games_in_exactly_x_days(4)
            six_days_games_list = self.database_handler.get_games_in_exactly_x_days(5)
            seven_days_games_list = self.database_handler.get_games_in_exactly_x_days(6)
            fourteen_days_games_list = self.database_handler.get_games_in_exactly_x_days(13)
            player_to_messages_map = dict()
        except NotifyAdminException:
            self.bot.sendMessage(self.admin_chat_id, 'Getting the 5 days game did not work, no schedules set for today')
        else:
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
        schedule.every().day.at("08:00").do(function)
    

    def send_stats_to_group_chat(self, function):
        schedule.every().day.at("22:00").do(function)


    def run_schedule(self):
        # method looped in ZWTelegramBot to run scheduled jobs
        schedule.run_pending()

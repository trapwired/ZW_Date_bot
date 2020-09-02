import schedule
import time
import telepot
import functools
import logging
from datetime import date

from DatabaseHandler import DatabaseHandler

class SchedulerHandler(object):

    def __init__(self, config, bot: telepot.Bot, db_handler: DatabaseHandler, _logger):
        # super().__init__()
        self.bot = bot
        self.group_id = config['API']['group_chat_id']
        self.database_handler = db_handler
        self.logger = _logger
        self.load_schedules()

        # since Pi restarts every 24hours, send error to admin if more than 24 hours up
        schedule.every(24).hours.do(self.send_reboot_failure)

        self.logger.info('Scheduler Handler started')


    def send_reboot_failure(self):
        self.bot.sendMessage(self.group_id, 'ERROR - Bot restart failed)')


    def load_schedules(self):
        # TODO load schedules from Database and add them to scheduler
        print('hi')


        # get all games that take place in next two weeks (minus the ones in less than 6 days)
        # remind all unsure players to edit_attendance for this game (send msg at 7am)
        seven_days_games_list = self.database_handler.get_games_in_between_x_y_days(5,14)
        # for (game_id, game_name) in seven_days_games_list:
        #    unsure_players_list = self.database_handler.get_unsure_players(game_id)
        #    for player_id in unsure_players_list:
                

        # get all games that take place in 7 days
        # remind all unsure players to edit attendance for this game (send msg at 7am)


        # get all games taking place in 5 days
        # remind all unsure players to edit attendance for this game (send msg at 7am)
        # set new scheduler to send message in half the time -> cancel if filled out -> same again

        # send stats_message to group chat at 20:00 (with wall of shame)

        
    
    def run_schedule(self):
        # method looped in ZWTelegramBot to run scheduled jobs
        schedule.run_pending()

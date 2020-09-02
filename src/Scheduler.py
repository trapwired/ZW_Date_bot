import schedule
import time
import telepot
import functools
import logging

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
        # schedule.every(10).seconds.do(self.logging_shutdown)

        # schedule.every(2).seconds.do(self.send_test)
        self.logger.info('SH  - Scheduler Handler started')


    def logging_shutdown(self):
        self.logger.shutdown()


    def send_reboot_failure(self):
        self.bot.sendMessage(self.group_id, 'ERROR - Bot restart failed)')


    def load_schedules(self):
        # TODO load schedules from Database and add them to scheduler
        print('hi')
    
        
    def run_schedule(self):
        # method looped in ZWTelegramBot to run scheduled jobs
        schedule.run_pending()

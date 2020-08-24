import schedule
import time
import telepot
import functools
import logging

from DatabaseHandler import DatabaseHandler

class SchedulerHandler(object):

    def __init__(self, config, bot: telepot.Bot, db_handler: DatabaseHandler):
        # super().__init__()
        self.bot = bot
        self.group_id = config['API']['group_chat_id']
        self.database_handler = db_handler
        self.load_schedules()

        schedule.every().day.at("08:00").do(self.send_test)
        # schedule.every().tuesday.at("14:00").do(self.send_ct)

        # schedule.every(2).seconds.do(self.send_test)
        logging.info('SH  - Scheduler Handler started')


    def send_test(self):
        self.bot.sendMessage(self.group_id, 'Good morning :)')


    def load_schedules(self):
        # TODO load schedules from Database and add them to scheduler
        print('hi')
    
        
    def run_schedule(self):
        # method looped in ZWTelegramBot to run scheduled jobs
        schedule.run_pending()

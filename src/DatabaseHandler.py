import mariadb
import sys
import configparser
import os
import logging 
import utility as util
import datetime
import time
import telepot

from exceptions import NotifyUserException, NotifyAdminException


class DatabaseHandler(object):

    def __init__(self, bot: telepot.Bot, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser, _logger: logging.Logger):
        self.config = config
        self.logger = _logger
        self.bot = bot
        self.admin_chat_id = api_config['API']['admin_chat_id']

        # Connect to MariaDB Platform
        try:
            connection = mariadb.connect(
                user=self.config['CONNECTION']['user'],
                password=self.config['CONNECTION']['password'],
                host=self.config['CONNECTION']['host'],
                port=int(self.config['CONNECTION']['port']),
                database=self.config['CONNECTION']['database']

            )
        except mariadb.Error as e:
            self.logger.error(f"Error connecting to MariaDB Platform: {e}")
            raise
        except:
            self.logger.error("Error in DB-Init", exc_info=True)
    
        # Get Cursor
        self.cursor = connection.cursor()
        self.connection = connection
        self.logger.info("DataBase Handler started")
        self.id_to_game = dict()

        # set timeouts to 24hours to prevent "Server gone away - error"
        try:
            self.cursor.execute('SET SESSION wait_timeout=86400;')
            self.cursor.execute('SET SESSION interactive_timeout=86400;')
        except:
            self.logger.warning(f"session parameters (timeouts) not set!", exc_info=True)
            # deal with it
 
        # build player dictionary for faster access of all player chat_id's
        self.player_chat_id_dict = self.init_player_chat_id_dict()


    def execute_mysql_without_result(self, mysql_statement: str, numberOfTries: int):
        """
        executes the mysql query given in mysql_statement - if it fails, it invokes itself with numberOfTries incremented by one
        if numberOfTries exceeds 2, an error is sent to admin_chat_id
        :param mysql_statement: a string containing the mysql query to execute on the database
        :param numberOfTries: a number between 0 and 3 indicating how many times the query was already tried to execute
        :raise NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """
        if numberOfTries > 2:
            raise NotifyUserException(mysql_statement)
        try:
            self.logger.info(f"Executing {mysql_statement}, numberOfTries = {numberOfTries}")
            self.cursor.execute(mysql_statement)
        except self.connection.Error as err:
            self.logger.error(f" Tried {mysql_statement} - {err}", exc_info=True)
        except:
            self.logger.error(f"Tried {mysql_statement}: ", exc_info=True)
        else:
            self.connection.commit()
            return

        self.connection.rollback()
        time.sleep(0.5)
        numberOfTries += 1
        self.execute_mysql_without_result(mysql_statement, numberOfTries)


    def execute_mysql_with_result(self, mysql_statement: str, numberOfTries: int):
        """
        executes the mysql query given in mysql_statement - if it fails, it invokes itself with numberOfTries incremented by one
        if numberOfTries exceeds 2, an error is sent to admin_chat_id
        :param mysql_statement: a string containing the mysql query to execute on the database
        :param numberOfTries: a number between 0 and 3 indicating how many times the query was already tried to execute
        :raise NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """
        if numberOfTries > 2:
            raise NotifyUserException(mysql_statement)
        try:
            self.logger.info(f"Executing {mysql_statement}, numberOfTries = {numberOfTries}")
            self.cursor.execute(mysql_statement)
        except self.connection.Error as err:
            self.logger.error(f" Tried {mysql_statement} - {err}", exc_info=True)
        except:
            self.logger.error(f"Tried {mysql_statement}: ", exc_info=True)
        else:
            return self.cursor

        self.connection.rollback()
        time.sleep(0.5)
        numberOfTries += 1
        return self.execute_mysql_with_result(mysql_statement, numberOfTries)


    def init_state_map(self):
        """
        initialize the state_map dictionary from DataBase State
        -1: Start, 0 = Overview, any other positive number: represents game is beeing edited (from chat_id to int)
        """
        state_map = dict()
        try:
            mysql_statement = "SELECT ID, State FROM Players;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            self.bot.sendMessage(self.admin_chat_id, f"Initialization of State Map failed\BOT NOT RUNNING")
            sys.exit(1)
        else:
            for (ID, State) in self.cursor:
                state_map[ID] = State
            return state_map


    def init_player_chat_id_dict(self):
        # get all player id's from the Database for faster access in queries involving chat_id's
        mysql_statement = "SELECT ID, LastName, FirstName FROM Players;"
        try:
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            self.bot.sendMessage(self.admin_chat_id, f"Initialization of Player to chat_id dictionary failed\BOT NOT RUNNING")
            sys.exit(1)
        else:
            player_dict = dict()
            for (ID, LastName, FirstName) in cursor:
                player_dict[ID] = f"{FirstName} {LastName[:1]}\\."
            return player_dict


    def get_games_in_between_x_y_days(self, start: int, end: int):
        # get all games that take place in the future between start and end days (including)
        # Get current date
        # SELECT DateTime, Place, Adversary FROM Games WHERE DateTime BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 500 DAY) ORDER BY DateTime ASC;    
        (player_columns, player_list) = self.get_player_columns()
        mysql_statement = f"SELECT DateTime, Place, Adversary, {player_columns} FROM Games WHERE DateTime BETWEEN DATE_ADD(CURDATE(), INTERVAL {start} DAY) AND DATE_ADD(CURDATE(), INTERVAL {end + 1} DAY) ORDER BY DateTime ASC;"

            
    def get_games_in_exactly_x_days(self, x: int):
        (player_columns, player_list) = self.get_player_columns()
        mysql_statement = f"SELECT DateTime, Place, Adversary, {player_columns} FROM Games WHERE DATE(DateTime) = DATE_ADD(CURDATE(), INTERVAL {x} DAY) ORDER BY DateTime ASC;"
        try:
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyAdminException
        else:
            result_tuple_list = []
            for row in cursor.fetchall():
                game_dateTime = row[0]
                game_place = row[1]
                game_adversary = row[2]
                unsure_chat_id_list = []
                count = 3
                for player in player_list:
                    player_status = row[count]
                    if player_status == 0:
                        unsure_chat_id_list.append(player)
                    count += 1
                game_info = f"{game_dateTime}|{game_adversary}|{game_place}"
                result_tuple_list.append((game_info, unsure_chat_id_list))
            return result_tuple_list


    def insert_new_player(self, chat_id: int, firstname: str, lastname: str):
        # Add new Player to Players
        # Add new column to Games
        # Add new Player to State Map
        try:
            new_column_name = f"p{chat_id}"
            mysql_statement = f"INSERT INTO Players(ID, FirstName, LastName, State) VALUES({chat_id},'{firstname}','{lastname}', -1);"
            self.execute_mysql_without_result(mysql_statement, 0)

            mysql_statement2 = f"ALTER TABLE Games ADD COLUMN {new_column_name} INT DEFAULT 0;"
            self.execute_mysql_without_result(mysql_statement2, 0)

            self.player_chat_id_dict[chat_id] = f"{firstname} {lastname[:1]}\\."
        except NotifyUserException:
            raise NotifyUserException
        

    def player_present(self, chat_id: int):
        try:
            mysql_statement = f"SELECT * FROM Players WHERE ID = {chat_id}"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            cursor.fetchall()
            return cursor.rowcount > 0

    
    def get_games_list_with_status(self, chat_id: int):
        # get ordered list of games in the future
        player_column = f"p{chat_id}"
        button_list = []
        button_list.append(['continue later'])
        try:
            mysql_statement = f"SELECT ID, DateTime, Place, {player_column} FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # pretty print columns, add to buttons
            for (ID, DateTime, Place, player_col) in cursor:
                button_list.append([util.pretty_print_game(DateTime, Place, player_col)])
                if ID not in self.id_to_game: 
                    self.id_to_game[ID] = f"{util.make_datetime_pretty(DateTime)}"
            return button_list

    
    def get_player_columns(self):
        player_columns = ''
        player_list = []
        for player_id in self.player_chat_id_dict:
            player_columns += f"p{player_id},"
            player_list.append(player_id)
        # delete last comma
        player_columns = player_columns[:len(player_columns)-1]
        return (player_columns, player_list)


    def get_stats_next_game(self):
        (player_columns, player_list) = self.get_player_columns()

        # now get next game for all players
        try:
            mysql_statement = f"SELECT DateTime, Place, Adversary, {player_columns} FROM Games WHERE DateTime > CURRENT_TIMESTAMP() ORDER BY DateTime ASC LIMIT 1;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            return_row = cursor.fetchone()
            result = ''
            # create 3 lists for Yes(1), No(2), Unsure(0)
            yes_list = []
            no_list = []
            unsure_list = []

            result = f"{util.make_datetime_pretty_md(return_row[0])} \\| {return_row[1]} \\| {return_row[2]}\n"
            count = 3
            for player in player_list:
                status = return_row[count]
                if status == 0:
                    unsure_list.append(self.player_chat_id_dict[player])
                elif status == 1:
                    yes_list.append(self.player_chat_id_dict[player])
                elif status == 2:
                    no_list.append(self.player_chat_id_dict[player])
                count += 1

            player_count = len(yes_list) + len(no_list) + len(unsure_list)
            # assemble result
            result += f"\n  *Team / Yes \\({len(yes_list)}/{player_count}\\)*:\n"
            if len(yes_list) > 0:
                for yes_player in yes_list:
                    result += f"        {yes_player}\n"
            else:
                result += "        No one yet\\!\n"
            if len(no_list) > 0:
                result += f"\n  *No \\({len(no_list)}/{player_count}\\)*:\n"
                for no_player in no_list:
                    result += f"        {no_player}\n"
            if len(unsure_list) > 0:
                result += f"\n  *Still Unsure \\({len(unsure_list)}/{player_count}\\)*:\n"
                for unsure_player in unsure_list:
                    result += f"        {unsure_player}\n"

            return result


    def insert_games(self):
        # Backup of all Games in case of DB reset
        games = []
        games.append(['2020-09-05 17:30:00', 'Zürich Saalsporthalle', 'TV Witikon'])
        games.append(['2020-09-12 17:30:00', 'Zürich Stettbach', 'Schwamendingen Handball'])
        games.append(['2020-10-31 17:30:00', 'Zürich Saalsporthalle', 'SG Albis Foxes'])
        games.append(['2020-11-14 16:30:00', 'Zürich Blumenfeld', 'TV Unterstrass'])
        games.append(['2020-11-21 14:00:00', 'Zürich Utogrund', 'HC Dübendorf'])
        games.append(['2020-11-28 19:30:00', 'Zürich Stettbach', 'TV Witikon'])
        games.append(['2020-12-13 10:45:00', 'Volketswil Gries', 'SC Volketswil'])
        games.append(['2021-01-16 14:00:00', 'Zürich Utogrund', 'Schwammendingen Handball'])
        games.append(['2021-03-06 15:00:00', 'Kilchberg Hochweid', 'SG Albis Foxes'])
        games.append(['2021-03-13 14:00:00', 'Zürich Utogrund', 'TV Unterstrass'])
        games.append(['2021-03_27 00:00:00', 'TBA', 'HC Dübendorf'])
        games.append(['2021-04-17 14:00:00', 'Zürich Utogrund', 'SC Volketswil'])
        
        try:
            for game in games:
                self.execute_mysql_without_result(game, 0)  
        except NotifyUserException:
            raise NotifyUserException


    def get_game_id(self, game: str):
        # reverse lookup in self.id_to_game dict
        for key, value in self.id_to_game.items():
            if game in value:
                return key
        # if not found in dict (for whatever reasons): lookup in Database
        # TODO
        return -1


    def edit_game_attendance(self, game_id: int, new_status: str, chat_id: int):
        """
        change the attendance-state for a game
        :param game_id: the ID of the game to change the attendance state for
        :param new_status: new attendance-state (YES, NO, UNSURE), needs to be translated to number
        :param chat_id: the chat_id of the player changing his attendance-state
        
        """
        new_status_translated = util.translate_status_from_str(new_status)
        player_column = f"p{chat_id}"
        mysql_statement = f" UPDATE Games SET {player_column} = {new_status_translated} WHERE ID = {game_id};"
        try:
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException


    def update_state(self, chat_id: int, new_state: int):
        """
        update state in database
        :param chat_id: chat_id of player to change state
        :param new_state: new state to change to
        """
        mysql_statement = f"UPDATE Players SET State = {new_state} WHERE ID = {chat_id};"
        try:
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException   

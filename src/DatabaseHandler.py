import mariadb
import sys
import configparser
import os
import logging
import datetime
import time
import re
import telepot

import utility as util
from exceptions import NotifyUserException, NotifyAdminException
from PlayerState import PlayerState
from StateObject import StateObject
from SpectatorState import SpectatorState


class DatabaseHandler(object):

    def __init__(self, bot: telepot.Bot, config: configparser.RawConfigParser, api_config: configparser.RawConfigParser,
                 _logger: logging.Logger):
        """initialize the DataBase Handler: establish connection to local database, set connection parameters, build player dictionary  for faster access

        Args:
            bot (telepot.Bot): main bot, used to send messages to admin in case of error
            config (configparser.RawConfigParser): provides credentials for database connection
            api_config (configparser.RawConfigParser): provides maintainer_chat_id
            _logger (logging.Logger): logger instance, the same over all modules, log to same file

        Raises:
            NotifyAdminException: if connection to local database can not be established
        """

        # initialize fields
        self.config = config
        self.logger = _logger
        self.bot = bot
        self.maintainer_chat_id = api_config['API']['maintainer_chat_id']
        self.group_chat_id = api_config['API']['group_chat_id']

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
            raise NotifyAdminException(e)
        except:
            self.logger.error("Error in DB-Init", exc_info=True)
            raise NotifyAdminException

        # Get Cursor and Connection
        self.cursor = connection.cursor()
        self.connection = connection
        self.logger.info("DataBase Handler started")

        # initialize id_to_game dictionary
        self.id_to_game = dict()

        # set timeouts to 24hours to prevent "Server gone away - error"
        try:
            self.cursor.execute('SET SESSION wait_timeout=86400;')
            self.cursor.execute('SET SESSION interactive_timeout=86400;')
        except:
            self.logger.warning(f"session parameters (timeouts) not set!", exc_info=True)
            self.bot.sendMessage(self.maintainer_chat_id, 'Session parameters not set, will timeout in 8 hours')

        # build player dictionary for faster access of all player chat_id's
        self.player_chat_id_dict = self.init_player_chat_id_dict()

    def execute_mysql_without_result(self, mysql_statement: str, numberOfTries: int):
        """Execute the mysql query given in mysql_statement - if it fails, it invokes itself with numberOfTries incremented by one
        if numberOfTries exceeds 2, an error is sent to maintainer_chat_id

        Args:
            mysql_statement (str): a string containing the mysql query to execute on the database
            numberOfTries (int): a number between 0 and 3 indicating how many times the query was already tried to execute

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """

        # raise NotifyUserException if unsuccesfully tried to execute statement 3 times
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
        # on fail: wait, increase number of tries and try again
        time.sleep(0.5)
        numberOfTries += 1
        self.execute_mysql_without_result(mysql_statement, numberOfTries)

    def execute_mysql_with_result(self, mysql_statement: str, numberOfTries: int):
        """executes the mysql query given in mysql_statement - if it fails, it invokes itself with numberOfTries incremented by one
        if numberOfTries exceeds 2, an error is sent to maintainer_chat_id

        Args:
            mysql_statement (str): a string containing the mysql query to execute on the database
            numberOfTries (int): a number between 0 and 3 indicating how many times the query was already tried to execute

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            mariadb.connection.cursor: the cursor object containing the database response
        """

        # raise NotifyUserException if unsuccesfully tried to execute statement 3 times
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
        # on fail: wait, increase number of tries and try again
        time.sleep(0.5)
        numberOfTries += 1
        return self.execute_mysql_with_result(mysql_statement, numberOfTries)

    def init_user_state_map(self):
        """initialize the state_map dictionary from DataBase 
        see State.py for translation

        Returns:
            dict(): a dictionary mapping from chat_id to state 
        """

        state_map = dict()
        try:
            mysql_statement = "SELECT ID, State FROM Players;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            self.bot.sendMessage(self.maintainer_chat_id, f"Initialization of Player State Map failed\BOT NOT RUNNING")
            sys.exit(1)
        else:
            for (ID, State) in cursor:
                state_map[ID] = StateObject(State)
            # self.logger.info(state_map)
            return state_map

    def init_spectator_state_map(self):
        """initialize the state_map dictionary from DataBase
        see State.py for translation

        Returns:
            dict(): a dictionary mapping from chat_id to state
        """

        state_map = dict()
        try:
            mysql_statement = "SELECT ID, State FROM Spectators;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"Initialization of Spectator State Map failed\BOT NOT RUNNING")
            sys.exit(1)
        else:
            for (ID, State) in cursor:
                state_map[int(ID)] = SpectatorState(State)
            # self.logger.info(state_map)
            return state_map

    def init_player_chat_id_dict(self):
        """get all player id's and names from the Database for faster access in queries involving chat_id's

        Returns:
            dict(): map from chat_id to Name
        """

        mysql_statement = "SELECT ID, LastName, FirstName FROM Players;"
        try:
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"Initialization of Player to chat_id dictionary failed\BOT NOT RUNNING")
            sys.exit(1)
        else:
            player_dict = dict()
            for (ID, LastName, FirstName) in cursor:
                # store Max M. for fast pretty printing status
                player_dict[ID] = f"{FirstName} {LastName[:1]}\\."
            return player_dict

    def get_games_in_exactly_x_days(self, x: int):
        """Query the Database to get all games taking place in exactly x days
        return a list of all players that are still unsure

        Args:
            x (int): get the game taking place in exactly x days

        Raises:
            NotifyAdminException: if a database access fails, raise exception to notify admin

        Returns:
            [([], [])]: return a list of tuples: for each game on this given day, return a tuple containing the games infos (tuple(0)) and the players still unsure (tuple(1))
        """

        (player_columns, player_list) = self.get_player_columns()
        mysql_statement = f"SELECT DateTime, Place, Adversary {player_columns} FROM Games WHERE DATE(DateTime) = DATE_ADD(CURDATE(), INTERVAL {x} DAY) ORDER BY DateTime ASC;"
        try:
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException as nuException:
            raise NotifyAdminException(nuException)
        else:
            result_tuple_list = []
            # iterate over rows in cursor (one row = one game)
            for row in cursor.fetchall():
                game_dateTime = row[0]
                game_place = row[1]
                game_adversary = row[2]
                unsure_chat_id_list = []
                count = 3
                # iterate over players, add them to unsure-list of their status is unsure
                for player in player_list:
                    player_status = row[count]
                    if player_status == 0:
                        unsure_chat_id_list.append(player)
                    count += 1
                game_info = [str(game_dateTime), game_adversary, game_place]
                result_tuple_list.append((game_info, unsure_chat_id_list))
            return result_tuple_list

    def insert_new_player(self, chat_id: int, firstname: str, lastname: str):
        """Add a new player to the database: add a new line to the Player-Table, add a new column to the Games-Table (col-name: f"p{chat_id}), add the player to the python-state-map§

        Args:
            chat_id (int): the Telegram chat_id of the player to add
            firstname (str): first name of player to add
            lastname (str): last name of player to add

        Raises:
            NotifyUserException: if a database access fails, raise exception to notify admin and user
        """

        if lastname == ' No Name Given' or firstname == ' No Name Given':
            # send message to admin indicating that no first/lastname is given 
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"remember to manually update the name of {firstname} {lastname}")

        try:
            # insert new player row into Players-Table
            new_column_name = f"p{chat_id}"
            mysql_statement = f"INSERT INTO Players(ID, FirstName, LastName, State) VALUES({chat_id},'{firstname}','{lastname}', {PlayerState.DEFAULT.value});"
            self.execute_mysql_without_result(mysql_statement, 0)

            # insert new column into Games-Table
            mysql_statement2 = f"ALTER TABLE Games ADD COLUMN {new_column_name} INT DEFAULT 0;"
            self.execute_mysql_without_result(mysql_statement2, 0)

            # add new player to player_chat_id_dict
            self.player_chat_id_dict[chat_id] = f"{firstname} {lastname[:1]}\\."

        except NotifyUserException:
            raise NotifyUserException

    def add_spectator(self, chat_id: int, firstname: str, lastname: str):
        """Add a new Spectator to the database: add a new line to the Spectator-Table

        Args:
            chat_id (int): the Telegram chat_id of the player to add
            firstname (str): first name of player to add
            lastname (str): last name of player to add

        Raises:
            NotifyUserException: if a database access fails, raise exception to notify admin and user
        """

        if lastname == ' No Name Given' or firstname == ' No Name Given':
            # send message to admin indicating that no first/lastname is given
            self.bot.sendMessage(self.maintainer_chat_id,
                                 f"remember to manually update the name of {firstname} {lastname}")

        try:
            # insert new player row into Spectator-Table
            mysql_statement = f"INSERT INTO Spectators(ID, FirstName, LastName, State) VALUES({chat_id},'{firstname}','{lastname}', {SpectatorState.AWAIT_APPROVE.value});"
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException

    def player_present(self, chat_id: int):
        """check and return if a player is already in the database

        Args:
            chat_id (int): chat_id of the player to search database for

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            bool: is the player present in the database? 
        """

        try:
            mysql_statement = f"SELECT * FROM Players WHERE ID = {chat_id}"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            cursor.fetchall()
            return cursor.rowcount > 0

    def get_games_list_for_spectator(self):
        """Assemble a list of all future games for a spectator

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [[]]: a list of lists containing the infos for each game
        """

        # get ordered list of games in the future
        button_list = [['continue later']]
        # make sure to have 'continue later' at top of button_list
        try:
            mysql_statement = f"SELECT DateTime, Place FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # pretty print columns, add to buttons
            for (DateTime, Place) in cursor:
                button_list.append([util.pretty_print_game(DateTime, Place)])
            return button_list

    def get_pending_spectators(self):
        """Assemble a list of all pending spectators

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [[]]: a list of lists containing the pending spectators
        """
        # get ordered list of games in the future
        button_list = [['continue later']]
        # make sure to have 'continue later' at top of button_list
        try:
            mysql_statement = f"SELECT ID, LastName, FirstName FROM Spectators WHERE State=-1;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # pretty print columns, add to buttons
            for (ID, LastName, FirstName) in cursor:
                button_list.append([f"{ID} | {LastName} {FirstName}"])
            self.logger.info(button_list)
            if len(button_list) > 1:
                return button_list
            else:
                return None

    def get_games_list_with_status_summary(self):
        """Assemble a list of all future games including the current status of the player with chat_id

        Args:
            chat_id (int): the chat_id of the player to get the list for (and status)

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [[]]: a list of lists containing the infos for each game
        """

        # get ordered list of games in the future
        button_list = [['continue later']]
        # make sure to have 'continue later' at top of button_list
        try:
            mysql_statement = f"SELECT * FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC;"
            cursor = self.execute_mysql_with_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException
        else:
            # pretty print columns, add to buttons
            for values_list in cursor:
                button_list.append([util.pretty_print_game_from_list(values_list)])
            return button_list

    def get_games_list_with_status(self, chat_id: int):
        """Assemble a list of all future games including the current status of the player with chat_id

        Args:
            chat_id (int): the chat_id of the player to get the list for (and status)

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            [[]]: a list of lists containing the infos for each game
        """

        # get ordered list of games in the future
        player_column = f"p{chat_id}"
        button_list = [['continue later']]
        # make sure to have 'continue later' at top of button_list
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
        """used by DataBase Handler to get a list of all players and all player-columns (p...) in the same order

        Returns:
            ([],[]): A tuple containing two lists, one with the player-columns [p1, p2...] and one with the players chat_ids
        """

        player_columns = ''
        player_list = []
        for player_id in self.player_chat_id_dict:
            player_columns += f", p{player_id}"
            player_list.append(player_id)
        return (player_columns, player_list)

    def get_stats_next_game(self):
        return self.get_stats_game(is_next=True)

    def get_stats_game(self, game_id: int = -1, is_next: bool = False):
        """return the summary for the next game in the future indicating which players will play and which won't

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified

        Returns:
            str: a string, pretty-printed with the status uf the next game
        """
        (player_columns, player_list) = self.get_player_columns()

        try:
            mysql_statement = f"SELECT DateTime, Place, Adversary {player_columns} FROM Games WHERE ID={game_id};"
            if is_next:
                mysql_statement = f"SELECT DateTime, Place, Adversary {player_columns} FROM Games WHERE DateTime > CURRENT_TIMESTAMP() ORDER BY DateTime ASC LIMIT 1;"
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

            # first row of result: pretty-printed game_infos
            result = f"{util.make_datetime_pretty_md(return_row[0])} \\| {return_row[1]} \\| {return_row[2]}\n"
            count = 3
            for player in player_list:
                # iterate over players, add to yes/no/unsure_list according to their status
                status = return_row[count]
                if status == 0:
                    unsure_list.append(self.player_chat_id_dict[player])
                elif status == 1:
                    yes_list.append(self.player_chat_id_dict[player])
                elif status == 2:
                    no_list.append(self.player_chat_id_dict[player])
                count += 1

            # total player count
            player_count = len(yes_list) + len(no_list) + len(unsure_list)

            # assemble result, loop over each list
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
        """Backup of all Games data in case reinsertion into DataBase is needed

        Raises:
            NotifyAdminException: General Error to tell DataBase Access failed, admin will be notified
        """
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
                mysql_statement = f"INSERT INTO Games(ID, DateTime, Place, Adversary) VALUES('{game[0]}','{game[1]}','{game[2]}');"
                self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyAdminException

    def get_game_id(self, game: str):
        """reverse lookup for the date-time-string of a game (i.e. 12.09.2020 12:30) to the ID (unique) in DataBase.Games

        Args:
            game (str): the date-time-string of the game to get id

        Raises:
            NotifyAdminException: General Error to tell DataBase Access failed, admin will be notified

        Returns:
            int: ID of game in DataBase.Games
        """
        regex = '(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} \|)'
        if re.match(regex, game):
            # reverse lookup in self.id_to_game dict
            for key, value in self.id_to_game.items():
                if game[:16] in value:
                    return key

            # if not found in dict: look up in Database
            try:
                dateTime = util.game_string_to_datetime(game[:16])
            except:
                return -1
            else:
                mysql_statement = f" SELECT ID FROM Games WHERE DateTime = '{dateTime}';"
                try:
                    cursor = self.execute_mysql_with_result(mysql_statement, 0)
                except NotifyUserException:
                    raise NotifyAdminException
                else:
                    return_row = cursor.fetchone()
                    game_id = return_row[0]
                    self.id_to_game[game_id] = game
                    return game_id
        else:
            return -1

    def edit_game_attendance(self, game_id: int, new_status: str, chat_id: int):
        """change the attendance-state for a game for a given player

        Args:
            game_id (int): the ID of the game to change the attendance state for
            new_status (str): new attendance-state (YES, NO, UNSURE), needs to be translated to number
            chat_id (int): the chat_id of the player changing his attendance-state

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """

        new_status_translated = util.translate_status_from_str(new_status)
        player_column = f"p{chat_id}"
        mysql_statement = f" UPDATE Games SET {player_column} = {new_status_translated} WHERE ID = {game_id};"
        try:
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException

    def update_player_state(self, chat_id: int, new_state: PlayerState):
        """update the state of a player in the database

        Args:
            chat_id (int): chat_id of player to change state
            new_state (PlayerState): new state to change to

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """

        mysql_statement = f"UPDATE Players SET State = {new_state.value} WHERE ID = {chat_id};"
        try:
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException

    def update_spectator_state(self, chat_id: int, new_state: SpectatorState):
        """update the state of a spectator in the database

        Args:
            chat_id (int): chat_id of player to change state
            new_state (PlayerState): new state to change to

        Raises:
            NotifyUserException: General Error to tell DataBase Access failed, user and admin will be notified
        """

        mysql_statement = f"UPDATE Spectators SET State = {new_state.value} WHERE ID = {chat_id};"
        try:
            self.execute_mysql_without_result(mysql_statement, 0)
        except NotifyUserException:
            raise NotifyUserException

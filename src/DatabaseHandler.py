import mariadb
import sys
import configparser
import os
import logging 
import utility as util
import datetime


class DatabaseHandler(object):

    def __init__(self, config: configparser.RawConfigParser, _logger):
        self.config = config
        self.logger = _logger
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
            self.logger.error(f"DB  - Error connecting to MariaDB Platform: {e}")
            raise
        except:
            self.logger.error("Error in DB-Init", exc_info=True)
    
        # Get Cursor
        self.cursor = connection.cursor()
        self.connection = connection
        self.logger.info("DB  - DataBase Handler started")
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


    def get_games_in_between_x_y_days(self, x: int, y: int):
        # get all games that take place in the future between x and y days (including)
        # Get current date
        if x == y:
            print('starting day is same as end day')
        else: 
            today = datetime.date.today()
            in_x_days = (today + datetime.timedelta(days=x)).strftime("%Y-%m-%d")
            in_y_days = (today + datetime.timedelta(days=y)).strftime("%Y-%m-%d")
            startDate = f"{in_x_days} 00:00:00"
            endDate = f"{in_y_days} 00:00:00"

    
    def init_player_chat_id_dict(self):
        # get all player id's from the Database for faster access in queries involving chat_id's
        try:
            self.cursor.execute(
                "SELECT ID, LastName, FirstName FROM Players"
            )
        except self.connection.Error as err:
            self.logger.error(f"Tried to get List of all Players\n{err}")
            raise
        except:
            self.logger.error("Error in init_player_chat_id_dict", exc_info=True)
            return
        
        player_dict = dict()
        for (ID, LastName, FirstName) in self.cursor:
            player_dict[ID] = f"{FirstName} {LastName[:1]}\\."
        return player_dict


    def insert_new_player(self, chat_id: int, firstname: str, lastname: str):
        # Add new Player to Players
        # Add new column to Games
        # Add new Player to State Map

        new_column_name = f"p{chat_id}"
        self.logger.info(f"trying to add player{firstname} {lastname}")
        try:
            self.cursor.execute(
                "INSERT INTO Players(ID, FirstName, LastName) VALUES(?,?,?);",
                (chat_id, firstname, lastname)
            )
            self.logger.info(f"Trying to add V1")
            self.cursor.execute(
                f"ALTER TABLE Games ADD COLUMN {new_column_name} INT DEFAULT 0;"
            )
            self.logger.info(f"Trying to add V2" )
            self.connection.commit()
            self.logger.info(f"Added new Player({firstname} {lastname}), added new col in Games, added to state map")
            self.player_chat_id_dict[chat_id] = f"{firstname} {lastname[:1]}\\."
            return True
        except self.connection.Error as err:
            self.connection.rollback()
            self.logger.error(f"Tried to add new Player({firstname} {lastname}) to database - failed - rollback\n\t{err}")
            raise
        except:
            self.logger.error("Rrror insert_new_player", exc_info=True)


    def player_present(self, chat_id: int):
        try:
            self.cursor.execute(
                f"SELECT * FROM Players WHERE ID = {chat_id}"
            )
            self.cursor.fetchall()
            return self.cursor.rowcount > 0
        except self.connection.Error as err:
            self.logger.warning(f"Player_present Database Error\{err}")
            raise
        except:
            self.logger.error("Error in player_present", exc_info=True)
             # TODO change what happens if for some reason player not in dict

    
    def get_games_list_with_status(self, chat_id: int):
        # get ordered list of games in the future
        player_column = f"p{chat_id}"
        button_list = []
        button_list.append(['continue later'])
        try:
            self.cursor.execute(
                f"SELECT ID, DateTime, Place, {player_column} FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC;"
            )
        except self.connection.Error as err:
            self.logger.error(f"Tried to get list of games for {player_column}\n\t{err}")
            raise
        except:
            self.logger.error("Error in get_games_list_with_status", exc_info=True)
            return button_list
        # pretty print columns, add to buttons
        for (ID, DateTime, Place, player_col) in self.cursor:
            button_list.append([util.pretty_print_game(DateTime, Place, player_col)])
            if ID not in self.id_to_game: 
                self.id_to_game[ID] = f"{util.make_datetime_pretty(DateTime)}"
        return button_list

    
    def get_stats_next_game(self):
        # get all players (chat_id, firstname, lastname)
        player_columns = ''
        for player_id in self.player_chat_id_dict:
            player_columns += f"p{player_id},"
        # delete last comma
        player_columns = player_columns[:len(player_columns)-1]

        # now get next game for all players
        try:
            self.cursor.execute(
                f"SELECT DateTime, Place, Adversary, {player_columns} FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC LIMIT 1;"
            )
        except self.connection.Error as err:
            self.logger.error(f"Tried to get next Game with status of all players\n{err}")
            raise
        except:
            self.logger.error("Error in get_stats_next_game(2)", exc_info=True)
            return
        return_row = self.cursor.fetchone()
        result = ''
        # split by comma to get list in same order as result from sql query
        player_columns = player_columns.split(',')
        # create 3 lists for Yes(1), No(2), Unsure(0)
        yes_list = []
        no_list = []
        unsure_list = []

        result = f"{util.make_datetime_pretty_md(return_row[0])} \\| {return_row[1]} \\| {return_row[2]}\n"
        count = 3
        for player in player_columns:
            player_chat_id = int(player[1:len(player)])
            status = return_row[count]
            if status == 0:
                unsure_list.append(self.player_chat_id_dict[player_chat_id])
            elif status == 1:
                yes_list.append(self.player_chat_id_dict[player_chat_id])
            elif status == 2:
                no_list.append(self.player_chat_id_dict[player_chat_id])
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
        
        for game in games:
            try:
                self.cursor.execute(
                    "INSERT INTO Games(DateTime, Place, Adversary) VALUES(?,?,?);", 
                (game[0],game[1], game[2])
                )
            except self.connection.Error as err:
                self.logger.error(f"Tried insert all games into DB \n\t{err}")  
                raise    
            except:
                self.logger.error("Error in insert_games", exc_info=True)
                return  
    

    def get_game_id(self, game: str):
        # reverse lookup in self.id_to_game dict
        for key, value in self.id_to_game.items():
            if game in value:
                return key
        # if not found in dict (for whatever reasons): lookup in Database
        # TODO
        return -1


    def edit_game_attendance(self, game_id: int, new_status: str, chat_id: int):
        new_status_translated = util.translate_status_from_str(new_status)
        player_column = f"p{chat_id}"
        try:
            self.cursor.execute(
                f" UPDATE Games SET {player_column} = {new_status_translated} WHERE ID = {game_id};"
            )
            self.connection.commit()
            self.logger.info(f"DB  - Updated Game {game_id} from {player_column} to {new_status_translated}")
            return True
        except self.connection.Error as err:
            self.connection.rollback()
            self.logger.error(f"Tried to edit game attendance for {player_column}\n\t{err}")
            raise
        except:
            self.logger.error("Error in edit_game_attendance", exc_info=True)
            return False


    def init_state_map(self):
        # sql query to init the state_map in main bot class
        # -1: Start, 0 = Overview, any other positive number: represents game is beeing edited (from chat_id to int)
        state_map = dict()
        try:
            self.cursor.execute(
                "SELECT ID, State FROM Players;"
            )
        except self.connection.Error as err:
            self.logger.error(f"Tried to init state map \n\t{err}")
            raise
        except:
            self.logger.error("Error in init_state_map", exc_info=True)
            return False
        for (ID, State) in self.cursor:
            state_map[ID] = State
        return state_map


    def update_state(self, chat_id: int, new_state: int):
        try:
            self.cursor.execute(
                f"UPDATE Players SET State = {new_state} WHERE ID = {chat_id};"
            )
        except self.connection.Error as err:
            self.logger.error(f"Tried to update state map \n\t{err}")
            raise
        except:
            self.logger.error("Error in update_state", exc_info=True)
            return False
        return True


def main():
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')
    # db_handler = DatabaseHandler(config)
    # db_handler.insert_new_player(3, 'Blibla', 'Blub')
    #  db_handler.insert_new_player(2, 'ralph', 'lauren')
    # db_handler.get_stats_next_game()
    # db_handler.connection.close()


if __name__ == "__main__":
        main()

    
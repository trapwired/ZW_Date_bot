import mariadb
import sys
import configparser
import os
import logging 
import utility as util


class DatabaseHandler(object):

    def __init__(self, config: configparser.RawConfigParser):
        self.config = config
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
            logging.error(f"DB  - Error connecting to MariaDB Platform: {e}")
            sys.exit(1)
    
        # Get Cursor
        self.cursor = connection.cursor()
        self.connection = connection
        logging.info("DB  - DataBase Handler started")
        # TODO change what happens if for some reason player not in dict
        self.id_to_game = dict()


    def insert_new_player(self, chat_id: int, firstname: str, lastname: str):
        # Add new Player to Players
        # Add new column to Games
        # Add new Player to State Map
        new_column_name = f"p{chat_id}"
        try:
            self.cursor.execute(
                "INSERT INTO Players(ID, FirstName, LastName) VALUES(?,?,?);",
                (chat_id, firstname, lastname)
            )
            self.cursor.execute(
                f"ALTER TABLE Games ADD COLUMN {new_column_name} INT DEFAULT 0;"
            )
            self.connection.commit()
            logging.info(f"DB  - Added new Player({firstname} {lastname}), added new col in Games, added to state map")
            return True
        except self.connection.Error as err:
            self.connection.rollback()
            logging.error(f"DB  - Tried to add new Player({firstname} {lastname}) to database - failed - rollback\n\t{err}")
            return False


    def player_present(self, chat_id: int):
        try:
            self.cursor.execute(
                f"SELECT * FROM Players WHERE ID = {chat_id}"
            )
            self.cursor.fetchall()
            return self.cursor.rowcount > 0
        except self.connection.Error as err:
            logging.warning(f"DB  - Player_present Database Error\{err}")

    
    def get_games_list_with_status(self, chat_id: int):
        # get ordered list of games in the future
        player_column = f"p{chat_id}"
        button_list = []
        try:
            self.cursor.execute(
                f"SELECT ID, DateTime, Place, {player_column} FROM Games WHERE DateTime > CURDATE() ORDER BY DateTime ASC;"
            )
        except self.connection.Error as err:
            logging.error(f"DB - Tried to get list of games for {player_column}\n\t{err}")
        # pretty print columns, add to buttons
        for (ID, DateTime, Place, player_col) in self.cursor:
            pretty_datetime = util.make_datetime_pretty(DateTime)
            pretty_status = util.translate_status_from_int(player_col)
            button_list.append([f"{pretty_datetime} at {Place} ({pretty_status})"])
            if ID not in self.id_to_game: 
                self.id_to_game[ID] = f"{pretty_datetime}"
        button_list.append(['continue later'])
        return button_list


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
                logging.error(f"DB - Tried insert all games into DB \n\t{err}")        
    

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
            logging.info(f"DB  - Updated Game {game_id} from {player_column} to {new_status_translated}")
            return True
        except self.connection.Error as err:
            self.connection.rollback()
            logging.error(f"DB - Tried to edit game attendance for {player_column}\n\t{err}")
            return False


    def init_state_map(self):
        # sql query to init the state_map in main bot class
        state_map = dict()
        try:
            self.cursor.execute(
                "SELECT ID, State FROM Players;"
            )
        except self.connection.Error as err:
            logging.error(f"DB - Tried to init state map \n\t{err}")
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
            logging.error(f"DB - Tried to update state map \n\t{err}")
            return False 
        return True


def main():
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')
    db_handler = DatabaseHandler(config)
    print(db_handler.init_state_map())
    db_handler.connection.close()

if __name__ == "__main__":
        main()

    
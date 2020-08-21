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
        self.chat_to_player_id_dict = self.init_chat_to_player_id()
        self.id_to_game = dict()


    def init_chat_to_player_id(self):
        # create a dictionary to quickly lookup player_id from chat_id
        chat_to_player_id_dict = dict()
        try:
            self.cursor.execute(
                "SELECT ID, chat_id from Players"
            )
        except mariadb.Error as e:
            logging.error(f"DB  - Error connecting to MariaDB Platform: {e}")

        for (ID, chat_id) in self.cursor:
            chat_to_player_id_dict[chat_id] = ID
        return chat_to_player_id_dict


    def insert_new_player(self, firstname: str, lastname: str, chat_id: int):
        try:
            self.cursor.execute(
                "INSERT INTO Players(FirstName, LastName, chat_id) VALUES(?,?,?);",
                (firstname, lastname, chat_id)
            )
            self.connection.commit()
            logging.info(f"DB  - Added new Player({firstname} {lastname}) to database")
        except self.connection.Error as err:
            self.connection.rollback()
            logging.error(f"DB  - Tried to add new Player({firstname} {lastname}) to database - failed - rollback\n\t{err}")
            return False
        self.cursor.execute(
            "SELECT ID FROM Players WHERE chat_id =?;",
            (chat_id,)
        ) 
        new_player_id = 0
        for ID in self.cursor:
            # there really can be only one
            new_player_id = ID[0]
        new_column_name = f"p{new_player_id}"
        # TODO what if only the second execute statement fails?

        # add to self.chat_to_player_id dict
        self.chat_to_player_id_dict[chat_id] = new_player_id
        # now add respective column to Games Table, default value = 0 (unsure)
        try:
            self.cursor.execute(
                f"ALTER TABLE Games ADD COLUMN {new_column_name} INT DEFAULT 0;"
            )
            self.connection.commit()
            logging.info(f"DB  - Added new Player-Column({new_column_name}) to database")
            return True
        except self.connection.Error as err:
            self.connection.rollback()
            logging.error(f"DB  - Tried to add new Player-Column in Games({new_column_name}) to database - failed - rollback \n\tERROR{err}")
            return False


    def player_present(self, chat_id: int):
        try:
            self.cursor.execute(
                "SELECT * FROM Players WHERE chat_id = %s", 
                (chat_id,)
            )
            self.cursor.fetchall()
            return self.cursor.rowcount > 0
        except:
            logging.warning("DB  - Player_present Database Error")

    
    def get_games_list_with_status(self, chat_id: int):
        # get ordered list of games in the future
        player_column = 'p' + str(self.chat_to_player_id_dict[chat_id])
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
            pretty_status = util.translate_status(player_col)
            button_list.append([f"{pretty_datetime} at {Place} ({pretty_status})"])
            if ID not in self.id_to_game: 
                self.id_to_game[ID] = f"{pretty_datetime}"
        return button_list
        # [['Game 1'], ['Game2'], ['Game3'], ['Game4'], ['Game5'], ['Game6'], ['Game7'], ['Game8']]


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


def main():
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')

    db_handler = DatabaseHandler(config)
    # lister = db_handler.get_games_list_with_status(56)
    # print(lister)
    # print(util.make_datetime_pretty('2020-09-05 17:30:00'))

    """
    cur.execute("DELETE FROM Players WHERE LastName = 'Weibel';")
    cur.execute("SELECT * FROM Players;")
    for (ID, LastName, FirstName, chat_id) in cur:
        print(f"ID: {ID}, First Name: {FirstName}, Last Name: {LastName}, chat_id: {chat_id}")

    """
    db_handler.connection.close()

if __name__ == "__main__":
        main()

    
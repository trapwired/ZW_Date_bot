import mariadb
import sys
import configparser
import os
import logging 


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
        

    def insert_new_player(self, firstname: str, lastname: str, chat_id: int):
        try:
            self.cursor.execute(
                "INSERT INTO Players(FirstName, LastName, chat_id) VALUES(?,?,?);",
                (firstname, lastname, chat_id)
            )
            self.connection.commit()
            logging.info(f"DB  - Added new Player({firstname} {lastname}) to database")
        except :
            self.connection.rollback()
            logging.error(f"DB  - Tried to add new Player({firstname} {lastname}) to database - failed - rollback")
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

def main():
    path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
    config = configparser.RawConfigParser()
    config.read(os.path.join(path, 'db_config.ini'), encoding='utf8')

    db_handler = DatabaseHandler(config)
    db_handler.insert_new_player('test1', 'lastname_test', 95)


    """
    cur.execute("DELETE FROM Players WHERE LastName = 'Weibel';")
    cur.execute("SELECT * FROM Players;")
    for (ID, LastName, FirstName, chat_id) in cur:
        print(f"ID: {ID}, First Name: {FirstName}, Last Name: {LastName}, chat_id: {chat_id}")

    """
    db_handler.connection.close()

if __name__ == "__main__":
        main()

    
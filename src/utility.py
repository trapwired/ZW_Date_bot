from datetime import datetime
import logging

# Final List of the possibilities for game attendance
ATTENDANCE = ['UNSURE', 'YES', 'NO']


def make_datetime_pretty(DateTime: datetime):
    """pretty print DateTime

    Args:
        DateTime (datetime): DateTime to pretty print, format: 2020-09-05 17:30:00

    Returns:
        str: pretty printed DateTime
    """

    return DateTime.strftime("%d.%m.%Y %H:%M")


def make_datetime_pretty_str(DateTime: str):
    """pretty print DateTime from string

    Args:
        DateTime (str): String to pretty print, format: 2020-09-05 17:30:00

    Returns:
        str: pretty printed DateTime
    """

    date_time_obj = datetime.strptime(DateTime, "%Y-%m-%d %H:%M:%S")
    return date_time_obj.strftime("%d.%m.%Y %H:%M")


def make_datetime_pretty_md(DateTime: datetime):
    """pretty print DateTime for use in Markdown

    Args:
        DateTime (datetime): DateTime to pretty print, format: 2020-09-05 17:30:00

    Returns:
        str: pretty printed DateTime, in markdown syntax
    """

    return DateTime.strftime("%d\\.%m\\.%Y %H\\:%M")


def translate_status_from_int(status: int):
    """Translate status-number to status-string

    Args:
        status (int): number describing status

    Returns:
        str: Status as string
    """

    return ATTENDANCE[status]


def translate_status_from_str(status: str):
    """Translate status from String to int

    Args:
        status (str): Status to translate

    Returns:
        int: translated status to int
    """

    status = status.upper()
    index = 0
    for stat in ATTENDANCE:
        if stat == status:
            return index
        index += 1
    logging.warning(f"got wrong status: {status}")
    return -1


def status_is_valid(status: str):
    """return whether a given status (str) is valid

    Args:
        status (str): status to validate

    Returns:
        bool: status valid?
    """

    status_upper = status.upper()
    return status_upper in ATTENDANCE


def pretty_print_game(DateTime: datetime, place: str, status: int = None):
    """pretty print game infos  

    Args:
        DateTime (datetime): dateTime of the game
        place (str): Place of the game
        status (int, optional): if not given, leave out, else append. Defaults to None.

    Returns:
        str: pretty-printed game 
    """
    if status is None:
        # don't include status
        pretty_dateTime = make_datetime_pretty(DateTime)
        return f"{pretty_dateTime} | {place}"
    else:
        # include status
        pretty_status = f"({translate_status_from_int(status)})"
        pretty_dateTime = make_datetime_pretty(DateTime)
        return f"{pretty_dateTime} | {place} | {pretty_status}"


def is_member_of_group(status: str):
    """check, whether a given status indicates group-association

    Args:
        status (str): status to check

    Returns:
        bool: is a person with status in this group?
    """

    possibleStati = ['creator', 'administrator', 'member', 'restricted']
    return status in possibleStati


def write_whitelist_to_file(user_whitelist: list):
    """export user_whitelist to the api.ini file, so its initialized on the next restart 

    Args:
        user_whitelist (list): list of int's representing the chat_id's of users
    """

    with open("/home/pi/Desktop/ZW_Date_bot/src/api.ini", "r+") as file:
        # read all lines
        lines = file.readlines()
        # place cursor at start of file
        file.seek(0)
        # loop over lines
        for line in lines:
            new_line = line
            # leave all lines as they are, except we encountered the stored chat_ids
            if line.startswith('user_whitelist = '):
                # write new whitelist
                new_line = 'user_whitelist = '
                for user_id in user_whitelist:
                    new_line += f"{str(user_id).strip()}, "
                # get rid of last comma
                new_line = new_line[:len(new_line) - 2] + '\n'
            file.write(new_line)
        # save new file (size)
        file.truncate()


def game_string_to_datetime(game: str):
    """convert a pretty-printed game-string back to a DateTime Object

    Args:
        game (str): date and time String, format: 12.09.2020 12:30

    Returns:
        str: String of game in format 2020-09-12 12:30:00
    """

    date_time_obj = datetime.strptime(game, "%d.%m.%Y %H:%M")
    return str(date_time_obj.strftime("%Y-%m-%d %H:%M:%S"))


def parse_user_dateTime(dateTime: str):
    """parse a user-submitted date for insertion into DataBase

    Args:
        dateTime (str): a string containing a dateTime in the format %d.%m.%Y %H:%M

    Returns:
        str: parsed dateTime to Database format
    """
    date_time_obj = datetime.strptime(dateTime, "%d.%m.%Y %H:%M")
    return date_time_obj.strftime("%Y-%m-%d %H:%M:%S")


def sum_infos(info_list: list):
    """generate a list of all strings in info_list, seperated by |

    Args:
        info_list (list): list of information to concatenate to a string

    Returns:
        str: string of all concatenated information
    """
    all_infos = ''
    for info in info_list:
        all_infos += info + '|'
    return all_infos[:(len(all_infos) - 1)]


def pretty_print_player_db(player_list):
    header_id = "ID"
    header_ln = "LastName"
    header_fn = "FirstName"
    header_state = "State"
    header_ret = "Retired"
    len_id = len(header_id)
    len_ln = len(header_ln)
    len_fn = len(header_fn)
    len_state = len(header_state)
    len_ret = len(header_ret)
    for (ID, fn, ln, state, ret) in player_list:
        len_id = max(len_id, len(str(ID)))
        len_ln = max(len_fn, len(ln))
        len_fn = max(len_fn, len(fn))
        len_state = max(len_state, len(str(state)))
        len_ret = max(len_ret, len(str(ret)))

    def pad_it(string, l, is_left=False):
        if is_left:
            return "  " * (l - len(string)) + string
        return string + "  " * (l - len(string))

    res = "Database dump for Players\n"
    res += f"{pad_it(header_id, len_id + 1)} " \
           f"{pad_it(header_fn, len_fn + 1)} " \
           f"{pad_it(header_ln, len_ln + 1)} " \
           f"{pad_it(header_state, len_state + 1)} " \
           f"{pad_it(header_ret, len_ret + 1)}\n\n"
    for (ID, fn, ln, state, ret) in player_list:
        res += f"{pad_it(str(ID), len_id + 1, True)} " \
               f"{pad_it(fn, len_fn + 1)} " \
               f"{pad_it(ln, len_ln + 1)} " \
               f"{pad_it(str(state), len_state + 1, True)} " \
               f"{pad_it(str(ret), len_ret + 1, True)}\n"
    return res


def pretty_print_player_states():
    res = f"Pretty printing player states:\n\n"
    with open("PlayerState.py", "r") as f:
        for line in f:
            if line.startswith("    ") and not line.startswith("     "):
                res += line
    return res

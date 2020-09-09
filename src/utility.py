from datetime import datetime
import logging


ATTENDANCE = ['UNSURE', 'YES', 'NO']


def make_datetime_pretty(DateTime: datetime):
    # DateTime is of the format: 2020-09-05 17:30:00
    # date_time_obj = datetime.strptime(DateTime, "%Y-%m-%d %H:%M:%S")
    return DateTime.strftime("%d.%m.%Y %H:%M")

def make_datetime_pretty_md(DateTime: datetime):
    # DateTime is of the format: 2020-09-05 17:30:00
    # date_time_obj = datetime.strptime(DateTime, "%Y-%m-%d %H:%M:%S")
    return DateTime.strftime("%d\\.%m\\.%Y %H\\:%M")



def translate_status_from_int(status: int):
    return ATTENDANCE[status]


def translate_status_from_str(status: str):
    status = status.upper()
    index = 0
    for stat in ATTENDANCE:
        if stat == status:
            return index
        index += 1
    logging.warning(f"got wrong status: {status}")
    return -1


def status_is_valid(status: str):
    status_upper = status.upper()
    return status_upper in ATTENDANCE


def pretty_print_game(DateTime: datetime, place: str, status: int):
    pretty_status = f"({translate_status_from_int(status)})"
    # pretty_status =  (pretty_status + 8 * ' ')[:8]
    pretty_dateTime = make_datetime_pretty(DateTime)
    # pretty_place = (place + ' ' * 21)[:21]
    return f"{pretty_dateTime} | {place} | {pretty_status}"
    

def is_member_of_group(status: str):
    possibleStati = ['creator', 'administrator', 'member', 'restricted']
    return status in possibleStati


def write_whitelist_to_file(user_whitelist: list):
    with open("/home/pi/Desktop/ZW_Date_bot/src/api.ini", "r+") as file:
        lines = file.readlines()
        file.seek(0)
        for line in lines:
            new_line = line
            if line.startswith('user_whitelist = '):
                # write new whitelist
                new_line = 'user_whitelist = '
                for user_id in user_whitelist:
                    new_line += f"{user_id}, "
                # get rid of last comma
                new_line = new_line[:len(new_line)-2] + '\n'
            file.write(new_line)
        file.truncate()
                



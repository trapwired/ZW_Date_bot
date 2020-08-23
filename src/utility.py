from datetime import datetime
import logging


ATTENDANCE = ['UNSURE', 'YES', 'NO']


def make_datetime_pretty(DateTime: datetime):
    # DateTime is of the format: 2020-09-05 17:30:00
    # date_time_obj = datetime.strptime(DateTime, "%Y-%m-%d %H:%M:%S")
    return DateTime.strftime("%d.%m.%Y %H:%M")



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



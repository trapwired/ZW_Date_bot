from datetime import datetime


def make_datetime_pretty(DateTime: datetime):
    # DateTime is of the format: 2020-09-05 17:30:00
    # date_time_obj = datetime.strptime(DateTime, "%Y-%m-%d %H:%M:%S")
    return DateTime.strftime("%d.%m.%Y %H:%M")



def translate_status(status: int):
    attendance = ['UNSURE', 'YES', 'NO']
    return attendance[status]
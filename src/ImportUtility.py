import icalendar


def parse_file(file):
    res = []
    icalfile = open(file, 'rb')
    gcal = icalendar.Calendar.from_ical(icalfile.read())
    for component in gcal.walk():
        if component.name == "VEVENT":
            summary = component.get('summary')
            description = component.get('description')
            location = component.get('location')
            startdt = component.get('dtstart').dt
            enddt = component.get('dtend').dt
            exdate = component.get('exdate')
            dateTime = startdt.strftime("%Y-%m-%d %H:%M:%S")
            adv = summary.split(' - ')[1] if summary.split(' - ')[2] == 'züri west handball 1' else summary.split(' - ')[2]
            temp = f"INSERT INTO Games(DateTime, Place, Adversary) VALUES('{dateTime}', '{location}', '{adv}');"
            res.append(temp)
    icalfile.close()
    return res

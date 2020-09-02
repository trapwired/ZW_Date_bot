#!/bin/bash

stop_bot () {
	ps -ef | grep "src/ZWTelegramBot.py" | grep -v grep | awk '{print $2}' | xargs -r kill
}

start_bot () {
	mv /home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_VERBOSE.log /home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_VERBOSE_$(date +%F-%H:%M:%S).log
	nohup /usr/bin/python3 /home/pi/Desktop/ZW_Date_bot/src/ZWTelegramBot.py > /home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_VERBOSE.log 2 >&1 &
}

case "$1"
in
restart)
	stop_bot
	start_bot
	;;
stop) 
	stop_bot
	;;
start) 
	start_bot
	;;
esac



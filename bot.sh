#!/bin/bash

case "$1"
in
stop) 
	ps -ef | grep "src/ZWTelegramBot.py" | grep -v grep | awk '{print $2}' | xargs -r kill
	;;
start) 
	mv /home/pi/Desktop/ZW_Date_bot/ZW_bot.log /home/pi/Desktop/ZW_Date_bot/logs/ZW_bot_$(date +%F-%H:%M).log
	nohup /usr/bin/python3 /home/pi/Desktop/ZW_Date_bot/src/ZWTelegramBot.py > /home/pi/Desktop/ZW_Date_bot/ZW_bot.log 2 >&1 &;;
esac

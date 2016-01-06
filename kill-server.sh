ps -e | grep server.py | awk '{ print $1; }' | xargs kill -9

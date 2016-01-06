#!/usr/bin/python

##
##  client.py
##
##  William Cheung, 01/06/2015 
##

import sys
import socket
import select

SERVER_HOST = 'localhost'
SERVER_PORT = 9006

DEFAULT_TIMEOUT = 3
DEFAULT_BUFSIZE = 4096

CONN_SOCK = None

def usage_exit():
	print 'Usage : ' +  __file__ + '  <-l USERNAME> | <-r>\n'
	sys.exit()

def error_exit(errx):
	print errx
	sys.exit()

def connect_to_server():
	global CONN_SOCK
	CONN_SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	CONN_SOCK.settimeout(2)
	try:
		CONN_SOCK.connect((SERVER_HOST, SERVER_PORT))
		CONN_SOCK.settimeout(None)
		return 1
	except:
		pass
	return 0

def _send_request(method, params):
	request = {'Method': method}
	request.update(params)
	CONN_SOCK.send(str(request))
	rset, _, _ = select.select([CONN_SOCK], [], [], DEFAULT_TIMEOUT)
	if CONN_SOCK in rset:
		data = CONN_SOCK.recv(DEFAULT_BUFSIZE)
		try:
			response = eval(str(data))
			if response['Method'] == method and response['Error'] == 'OK':
				return response['Content']
		except:
			pass
	return None

def send_request(method, params):
	try: 
		ret = _send_request(method, params)
	except:
		error_exit('Connection is broken')
	return ret

def send_message(channel, message):
	request = {'Method':'MESSAGE', 'Channel': channel, 'Message': message}
	CONN_SOCK.send(str(request))

def channel_loop(channel):
	sys.stdout.write('[Me] '); sys.stdout.flush()
	while 1:
		socket_list = [sys.stdin, CONN_SOCK]
		rlist, _, _ = select.select(socket_list , [], [], 1)
		for sock in rlist:
			if sock == CONN_SOCK:
				data = sock.recv(DEFAULT_BUFSIZE)
				if not data:
					print '\nDisconnected from chat server'
					return
				else:
					try:
						msg = eval(str(data)) 
						if msg['Channel'] == channel:
							sys.stdout.write('\r[' + msg['Username'] + '] ')
							sys.stdout.write(msg['Message'])
					except:
						sys.stdout.write('\rReceived corrupted data from server\n')
					sys.stdout.write('[Me] '); sys.stdout.flush() 
			else:
				mymsg = sys.stdin.readline()
				if mymsg.strip() == '\\exit':
					leave_channel(channel)
					return
				if mymsg.strip() != '':
					send_message(channel, mymsg)
				sys.stdout.write('[Me] '); sys.stdout.flush()

def leave_channel(chan):
	if chan == 'w':
		return
	request = {'Method': 'LEAVE_CHANNEL', 'Channel': chan}
	return CONN_SOCK.send(str(request))

def do_login(username, password):
	params = {'Username': username, 'Password': password}
	return send_request('LOGIN', params)
 
def do_register(username, password):
	params = {'Username': username, 'Password': password}
	return send_request('REGISTER', params)

def login(username, password):
	if not connect_to_server():
		error_exit('Unable to connect to the server')
	if do_login(username, password):
		command_loop()
	else:
		error_exit('Unable to login')

def register(username, password):
	if not connect_to_server():
		error_exit('Unable to connect to the server')
	if do_register(username, password):
		command_loop()
	else:
		error_exit('Unable to register the new account')


ERROR_OK, ERROR_INVCMD, ERROR_OTHERS = 0, 1, 2
def command_loop():
	sys.stdout.write('> '); sys.stdout.flush()
	while 1:
		command = sys.stdin.readline().strip()
		if command == 'exit':
			sys.exit()
		elif command: 
			status = parse_and_execute(command)
			if status == ERROR_INVCMD:
				print 'Invalid command'
		sys.stdout.write('> '); sys.stdout.flush()

def parse_and_execute(command):
	tokens = command.split()
	nargs = len(tokens)
	op = tokens[0]
	if op == 'wrld' and nargs == 1:
		channel_loop('w')
	elif op == 'room':
		if nargs == 2 and tokens[1] == 'list':
			rooms = fetch_room_list()
			if rooms is None:
				print 'FetchRoomListError'
				return ERROR_OTHERS
			display_rooms(rooms)
		elif nargs == 3 and tokens[1] == 'join':
			if not join_room(tokens[2]):
				print 'JoinRoomError'
				return ERROR_OTHERS
			channel_loop('r#' + tokens[2])
		elif nargs == 3 and tokens[1] == 'make':
			if not make_room(tokens[2]):
				print 'MakeRoomError'
				return ERROR_OTHERS
		else:
			return ERROR_INVCMD
	elif op == 'help':
		display_help()
	else:
		return ERROR_INVCMD
	return ERROR_OK

def fetch_room_list():
	response = send_request('FETCH_ROOMS', {})
	try: 
		rooms = eval(response)
		if not isinstance(rooms, list):
			return None
		return rooms
	except:
		pass
	return None
		
def join_room(room):
	return send_request('JOIN_ROOM', {'Roomname': room})

def make_room(room):
	return send_request('MAKE_ROOM', {'Roomname': room})

def display_rooms(rooms):
	if not rooms:
		print 'No rooms found'
	else:
		for room in rooms:
			print room

def display_help():
	file = open('help.txt', 'r')
	sys.stdout.write(file.read())
	sys.stdout.flush()
	file.close()

def chat_client():
	argc = len(sys.argv)
	if argc < 2:
		usage_exit()
	if argc == 3 and sys.argv[1] == '-l':
		login(sys.argv[2], raw_input('Password: '))
	elif argc == 2 and sys.argv[1] == '-r':
		username = raw_input('Username: ')
		register(username, raw_input('Password: '))
	else:
		usage_exit()

if __name__ == "__main__":
    sys.exit(chat_client())

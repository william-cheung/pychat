#!/usr/bin/python

##  
##  server.py
##
##  William Cheung, 01/06/2016
##

import sys
import socket
import select
import bsddb
import time        # for time.time, time.ctime
import random      # for random.randint
import threading   # for threading.Lock, threading.Timer

DEBUG = 3
def debug_print(message, level): 
	if level < DEBUG:
		print message

HOST = ''       # hostname of the server
PORT = 9006     # port on which the server is listenning    

SERVER_SOCK = None   # server socket 
RECV_BUFFER = 4096   # default receiving buffer size of server socket

_21GAME_CHAN = 'r#21game'  # channel on which 21game is published

general_lock = threading.Lock()  # lock for threading-safety 

uind_db = bsddb.btopen('uind.db', 'c')  # table that holds basic info of users 
room_db = bsddb.btopen('room.db', 'c')  # table that holds basic info of chatting rooms
user_map = {}   # map : socket address (string) -> username 
conn_map = {}   # map : username -> connection socket   
onlt_map = {}   # map : username -> online time from the latest login

sock_lst = {}   # map : channel ('w', 'r#ROOMNAME', ...) -> list of connection sockets


# processing request from clients; no exceptions will be raised from this func
def request_handler(conn, req):
	debug_print(str(req), 2)
	general_lock.acquire()
	try:
		__request_handler(conn, req)
	except Exception as e:
		debug_print('Exception when processing request ' + str(req), 1)
		debug_print(e, 1)
	finally:
		general_lock.release()

# request dispatcher
def __request_handler(conn, req):
	method = req['Method']
	if method == 'LOGIN':
		login_handler(conn, req['Username'], req['Password'])
	elif method == 'REGISTER':
		register_handler(conn, req['Username'], req['Password'])
	elif method == 'MESSAGE':
		message_handler(conn, req['Channel'], req['Message'])
	elif method == 'MAKE_ROOM':
		make_room_handler(conn, req['Roomname'])
	elif method == 'JOIN_ROOM':
		join_room_handler(conn, req['Roomname'])
	elif method == 'FETCH_ROOMS':
		fetch_rooms_handler(conn)
	elif method == 'LEAVE_CHANNEL':
		leave_chan_handler(conn, req['Channel'])
	else:
		debug_print('Invalid request from ' + get_peername(conn), 1) 
		
		
def login_handler(conn, username, password):
	if auth_account(username, password):
		on_user_login(conn, username)
		conn.send(make_response('LOGIN', 'OK', None)) 

def register_handler(conn, username, password):
	if add_account(username, password):
		on_user_login(conn, username)
		conn.send(make_response('REGISTER', 'OK', None))
	
def message_handler(conn, channel, message):
	if channel == _21GAME_CHAN and message.startswith('\\21game '):
		process_21game_answer(conn, message[8:].strip())
	else:
		message_obj = make_message(channel, get_username(conn), message)
		broadcast(str(message_obj), channel, [conn])

# get channel identifier of a chatting room
def make_roomtag(roomname):
	return 'r#' + roomname

def make_room_handler(conn, roomname):
	if room_db.has_key[roomname]:
		return
	room = {'roomname': roomname, \
		'creater':get_username(conn), 'creation_date': time.ctime()}
	room_db[roomname] = str(room)
	room_db.sync()
	sock_lst[make_roomtag(roomname)] = []
	conn.send(make_response('MAKE_ROOM', 'OK', None))

def join_room_handler(conn, roomname):
	roomtag = make_roomtag(roomname)
	if sock_lst.has_key(roomtag):
		sock_lst[roomtag].append(conn)
		conn.send(make_response('JOIN_ROOM', 'OK', None))
		broadcast(make_message(roomtag, 'pychat', \
		                       'user [%s] entered our chatting room\n' % get_username(conn)), \
		          roomtag, [conn])	 

def fetch_rooms_handler(conn):
	xlist = []
	for _, v in room_db.iteritems():
		xlist.append(v)
	conn.send(make_response('FETCH_ROOMS', 'OK', xlist))
		
def leave_chan_handler(conn, channel):
	if conn in sock_lst[channel]:
		sock_lst[channel].remove(conn)
		if channel.startswith('r#'):
			broadcast(make_message(channel, 'pychat', \
			                       'user [%s] left our chatting room\n' % get_username(conn)), \
			          channel, [conn]) 		    
	else:
		debug_print('Error in : leave_chan_handler', 1)

def make_response(method, error, data):
	rsp = {'Method': method, 'Error': error}
	if data is None:
		rsp['Content'] = '(null)'
	else:
		rsp['Content'] = str(data)
	return str(rsp)

def make_message(channel, username, message):
	msg_obj = {'Channel': channel, 'Username': username, 'Message': message}
	return str(msg_obj)

def get_peername(conn):
	return str(conn.getpeername())

def get_username(conn):
	prname = get_peername(conn)
	return user_map[prname]

def add_account(username, password):
	if uind_db.has_key(username):
		return 0
	info = {'password': password, 'online_time': 0.0}
	uind_db[username] = str(info)
	uind_db.sync()
	return 1

def auth_account(username, password):
	if not uind_db.has_key(username):
		return 0
	info = eval(uind_db[username])
	if info['password'] != password:
		return 0
	return 1

def acc_online_time(username, t_in_secs):
	info = eval(uind_db[username])
	info['online_time'] += t_in_secs
	uind_db[username] = str(info)
	uind_db.sync()

def on_user_login(conn, username):
	prname = get_peername(conn)
	user_map[prname] = username
	conn_map[username] = conn
	onlt_map[username] = time.time()
	debug_print('User [%s] is online' % username, 2)

def on_user_leave(conn):
	prname = get_peername(conn)
	if not user_map.has_key(prname):
		return
	username = user_map[prname]
	t = time.time() - onlt_map[username]
	acc_online_time(username, t)
	del user_map[prname]
	del conn_map[username]
	del onlt_map[username]
	debug_print('User [%s] is offline' % username, 2)

def chat_server():

	global SERVER_SOCK
	SERVER_SOCK = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	SERVER_SOCK.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	SERVER_SOCK.bind((HOST, PORT))
	SERVER_SOCK.listen(10)

	# initialize sock_lst
	sock_lst['w'] = []
	sock_lst['w'].append(SERVER_SOCK)
	for r in room_db.keys():
		sock_lst[make_roomtag(r)] = []
	
	# start 21game service
	start_21game_service()

	while 1:
		rset, _, _ = select.select(sock_lst['w'], [], [], 0)
		
		for sock in rset:
            # a new connection request recieved
			if sock == SERVER_SOCK:
				sockfd, addr = SERVER_SOCK.accept()
				sock_lst['w'].append(sockfd)
				debug_print(str(addr) + ' connected', 2)
			else:
				try:
					reqst = sock.recv(RECV_BUFFER)
					if reqst:
                        # there is a request in the socket
						request_handler(sock, eval(str(reqst)))	
					else:
                        # no data means probably the connection has been broken
						on_user_leave(sock)
                # exception, broken socket connection
				except:
					on_user_leave(sock)
					continue

	server_socket.close()

# broadcast chat messages to all connected clients in a specific channel
def broadcast(message, channel, excludes):
	for socket in sock_lst[channel]:
		if socket != SERVER_SOCK and socket not in excludes:
			try:
				socket.send(str(message))
			except:
                # broken socket connection
				socket.close()
                # broken socket, remove it
				if socket in sock_lst[channel]:
					sock_lst[channel].remove(socket)



## --------------------------------------------------------------------------------   
##    
##      code for 21game service 
##
## --------------------------------------

_21GAME_INTERVAL = 60 # time interval between two consecutive rounds
_21GAME_DURATION = 30 # duration of each round

# class that encapsulates the properties of a round of 21game
class _21game_clazz:
	def __init__(self):
		self.rep = []
		self.winner = ''
		self.best_answer = 0
		self.running = 0
		self.players = []
		
_21game = _21game_clazz() # global object

def process_21game_answer(conn, answer):
	if not _21game.running:
		conn.send(make_message(_21GAME_CHAN, 'pychat', \
			'21game is not running now\n'))
		return 
	if conn in _21game.players:
		conn.send(make_message(_21GAME_CHAN, 'pychat', \
			'you have submmitted your answer\n'))
		return 
	_21game.players.append(conn)
	x = eval_21game_answer(answer)
	if x <= 21:
		if x > _21game.best_answer:
			_21game.best_answer = x
			_21game.winner = get_username(conn)
		conn.send(make_message(_21GAME_CHAN, 'pychat', \
			'your answer (%d) is submitted\n' % x))
	else:
		conn.send(make_message(_21GAME_CHAN, 'pychat', \
			'your answer is invalid\n'))

def eval_21game_answer(answer):
	fail = 24
	if not _21game.rep:
		return fail
	n = len(answer)
	i, s = 0, []
	while i < n:
		if answer[i].isdigit():
			j = i
			while j < n and answer[j].isdigit():
				j += 1
			s.append(eval(answer[i:j]))
			i = j + 1
		elif answer[i] in '+-*/() ':
			i += 1
		else:
			return fail
	if s == _21game.rep:
		try:
			x = eval(answer)
		except:
			return fail
		return x
	return fail

def start_21game_service():
	now = int(time.time())
	wait = (now + _21GAME_INTERVAL - 1) // _21GAME_INTERVAL * _21GAME_INTERVAL - now
	def the_service():
		threading.Timer(_21GAME_INTERVAL, _21game_publisher).start()
	threading.Timer(wait, the_service).start()

def _21game_publisher():
	general_lock.acquire()
	_21game.rep = make_21game()
	_21game.winner, _21game.best_answer = '', 0
	_21game.running = 1
	_21game.players = []
	broadcast(make_message(_21GAME_CHAN, 'pychat', \
	                       'a new 21game begins : %s\n' % str(_21game.rep)), \
	          _21GAME_CHAN, [])
	general_lock.release()
	debug_print('A new round of 21game is started : ' + time.ctime(), 2)
	threading.Timer(_21GAME_DURATION, _21game_judge).start()
	threading.Timer(_21GAME_INTERVAL, _21game_publisher).start()


def _21game_judge():
	debug_print('21game judge begins : ' + time.ctime(), 2)
	general_lock.acquire()
	_21game.running = 0
	if _21game.rep:
		if _21game.winner:
			broadcast(make_message(_21GAME_CHAN, 'pychat', \
			              'the winner of the last round 21game is [%s] whose answer is %d\n' \
				          % (_21game.winner, _21game.best_answer)), \
			          _21GAME_CHAN, [])
	general_lock.release()

def make_21game():
	ret = [1, 2, 5, 10]
	for i in range(len(ret)):
		ret[i] = random.randint(1, 10)
	ret.sort()
	return ret

if __name__ == "__main__":
    sys.exit(chat_server())

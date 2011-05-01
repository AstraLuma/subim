#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
The underlying protocol for SubIM, called the AstroIM Protocol.
"""
# SubIM, A dirt simple IM program for your local subnet.
# Copyright (C) 2007 James Bliss <james.bliss@astro73.com>
# 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
# 

#from __future__ import with_statement Compatibility with debian stable
from __future__ import division
import gtk
import gobject
gtk.gdk.threads_init()
gobject.threads_init()
import os, sys, socket, struct, threading
import logging, traceback, datetime

__author__ = "James Bliss <astronouth7303@gmail.com>"
__date__ = """$Date: 2007-09-16 15:49:47 -0400 (Sun, 16 Sep 2007) $"""
__version__ = """$Revision: 46 $"""

# These 4 variables are settings, you may configure them as you wish.

# The IPv4 multicast group is 224.0.0.0/4
# The mcast.py demo uses 225.0.0.250, which is part of a reserved block
# The link scope is 239.255.0.0/16, the organization scope is 239.192.0.0/14
# I'm going to use the former, with the last 2 bytes being map(ord, 'SI'), 
# SI = SubIM, or 239.255.83.73; this should work for home networks
SUBIM_GROUP = '239.255.83.73'
# Set this to the number of hops packets can take. 1 is fine for most homes,
# Organizations or other more complex setups may need higher numbers.
SUBIM_TTL = 3

# Change this to 8123 to test with mcast.py found in the Python demos
# 5349 = "%02X%02X" % tuple(map(ord, 'SI')), SI = SubIM
SUBIM_PORT = 5349

HEADER_FORMAT = "!H"
ARGUMENT_FORMAT = "!L"

CMD_MESSAGE = 0
CMD_USER_JOIN = 1 # Also used as the response for a user list request
CMD_USER_PART = 2
CMD_LIST_USERS = 3
CMD_APP_MESSAGE = 4 # Similar to MESSAGE, but for application communication

class Protocol(object):
	sock = None
	
	joiners = []
	parters = []
	msgers = []
	appers = []
	joined = False
	
	name = None
	group = SUBIM_GROUP
	port = SUBIM_PORT
	
	def __init__(self, name, **kwargs):
		self.name = name
		
		# Load options
		self.group = kwargs.get('group', SUBIM_GROUP)
		self.port = kwargs.get('port', SUBIM_PORT)
		ttl = kwargs.get('ttl', SUBIM_TTL)
		
		# Sending stuff
		self.sock = Protocol._openmcastsock(self.group, self.port)
		ttl = struct.pack('b', ttl) # Time-to-live
		self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
		self.joined = False
		
		self.joiners = []
		self.parters = []
		self.msgers = []
		self.appers = []
	
	@staticmethod
	def _openmcastsock(group, port):
		"""
		Open a UDP socket, bind it to a port and select a multicast group
		Borrowed from the Python demos.
		"""
		#
		# Create a socket
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		#
		# Allow multiple copies of this program on one machine
		# (not strictly needed)
		s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		#
		# Bind it to the port
		s.bind(('', port))
		#
		# Look up multicast group address in name server
		# (doesn't hurt if it is already in ddd.ddd.ddd.ddd format)
		group = socket.gethostbyname(group)
		#
		# Construct binary group address
		bytes = map(int, group.split("."))
		grpaddr = 0
		for byte in bytes: grpaddr = (grpaddr << 8) | byte
		#
		# Construct struct mreq from grpaddr and ifaddr
		ifaddr = socket.INADDR_ANY
		mreq = struct.pack('ll', socket.htonl(grpaddr), socket.htonl(ifaddr))
		#
		# Add group membership
		s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
		#
		return s
	
	def __encode(self, uni):
		return unicode(uni).encode('utf8', 'ignore') # We really shouldn't get anything
	
	def __decode(self, data):
		return unicode(data, 'utf8', 'ignore')
	
	# SENDING #
	def __send(self, cmd, *args):
		args = map(unicode, args)
		logging.getLogger('astroim.Protocol.__send').log(logging.DEBUG, "%r %r", cmd, args)
		data = struct.pack(HEADER_FORMAT, cmd)
		args = [self.name] + args # Prefix the username to the args
		for a in args:
			d = self.__encode(a)
			data += struct.pack(ARGUMENT_FORMAT, len(d))
			data += d
		self.sock.sendto(data, (self.group, self.port))
	
	def sendMessage(self, msg):
		logging.getLogger('astroim.Protocol.sendMessage').log(logging.DEBUG, "%r", msg)
		self.__send(CMD_MESSAGE, msg)
	
	def listUsers(self):
		logging.getLogger('astroim.Protocol.listUsers').log(logging.DEBUG, "entry")
		#self.userJoin(getHost()) Shouldn't be needed, we'll reply to our own list
		self.__send(CMD_LIST_USERS)
	
	def join(self):
		logging.getLogger('astroim.Protocol.join').log(logging.DEBUG, "entry")
		self.__send(CMD_USER_JOIN)
		self.joined = True
	
	def part(self):
		logging.getLogger('astroim.Protocol.part').log(logging.DEBUG, "entry")
		self.joined = False
		self.__send(CMD_USER_PART)
	
	def sendAppMsg(self, app, msg):
		logging.getLogger('astroim.Protocol.sendApp').log(logging.DEBUG, "%r", msg)
		self.__send(CMD_APP_MESSAGE, app, msg)

	
	# RECEIVING #
	def recieveMessage(self, timestamp, src, user, msg):
		logging.getLogger('astroim.Protocol.recieveMessage').log(logging.DEBUG, "%r %r", user, msg)
		for c in self.msgers:
			if callable(c): c(timestamp, user, msg)
	
	def userJoin(self, timestamp, src, user):
		logging.getLogger('astroim.Protocol.userJoin').log(logging.DEBUG, "%r", user)
		for c in self.joiners:
			if callable(c): c(timestamp, user)
	
	def userPart(self, timestamp, src, user):
		logging.getLogger('astroim.Protocol.userPart').log(logging.DEBUG, "%r", user)
		for c in self.parters:
			if callable(c): c(timestamp, user)
		# If they're using the same name, send out a join message (we're still here)
		if user == getHost() and self.joined:
			self.join()
	
	def __reply2list(self, timestamp, src, user):
		self.__send(CMD_USER_JOIN)
	
	def recieveAppMsg(self, timestamp, src, user, app, msg):
		logging.getLogger('astroim.Protocol.recieveAppMsg').log(logging.DEBUG, "%r %r %r", user, app, msg)
		for c in self.appers:
			if callable(c): c(timestamp, user, app, msg)
	
	COMMANDS = {
		CMD_MESSAGE : recieveMessage,
		CMD_USER_JOIN : userJoin,
		CMD_USER_PART : userPart,
		CMD_LIST_USERS : __reply2list,
		CMD_APP_MESSAGE : recieveAppMsg, 
	}
	
	def __readPacket(self):
		dlen = struct.calcsize(HEADER_FORMAT)
		d,src = self.sock.recvfrom(4096)
		timestamp = datetime.datetime.now()
		logging.getLogger('astroim.Protocol.__readPacket').log(logging.DEBUG, "%r %s",d,src)
		cmd, = struct.unpack(HEADER_FORMAT, d[:dlen])
		d = d[dlen:]
		args = []
		alen = struct.calcsize(ARGUMENT_FORMAT)
		while len(d) >= alen:
			l, = struct.unpack(ARGUMENT_FORMAT, d[:alen])
			d = d[alen:]
			# FIXME: Handle blobs
			args.append(self.__decode( d[:l] ))
			d = d[l:]
		if len(d):
			logging.getLogger('astroim.Protocol.__readPacket').log(logging.WARNING, "Leftover data: %r", d)
		if len(args) < 1:
			logging.getLogger('astroim.Protocol.__readPacket').log(logging.WARNING, "No user found")
			user = None
		else:
			user = args[0]
			args = args[1:]
		return timestamp, src, cmd, user, args
	
	def readOne(self):
		timestamp, src, cmd, user, args = self.__readPacket()
		logging.getLogger('astroim.Protocol.readOne').log(logging.DEBUG, "%r %r %r %r", src, cmd, user, args)
		if cmd in self.COMMANDS:
			self.COMMANDS[cmd](self, timestamp, src, user, *args)
	
	def readForever(self):
		logging.getLogger('astroim.Protocol.readForever').log(logging.INFO, "Start reading")
		while True:
			try:
				self.readOne()
			except Exception, err:
				logging.getLogger('astroim.Protocol.readForever').log(logging.DEBUG, "%s %s", type(err), err)
				traceback.print_exc()
	
	def startReading(self):
		t = threading.Thread(target=self.readForever, name="SocketReader")
		t.setDaemon(True)
		t.start()
	
	def __enter__(self):
		self.join()
	
	def __exit__(self, exc_type=None, exc_value=None, traceback=None):
		self.part()


#!/usr/bin/env python
# coding=utf-8
# Contributor:
#      TODO

__version__ = '1.0.1'


import sys
import os
import re
import time
import struct
import zlib
import logging

import errno
import threading 

try:
    from io import BytesIO
except ImportError:
    from cStringIO import StringIO as BytesIO
try:
    from google.appengine.api import urlfetch
    from google.appengine.runtime import apiproxy_errors
except ImportError:
    urlfetch = None
try:
    import sae
except ImportError:
    sae = None
try:
    import socket
    import select
except ImportError:
    socket = None
try:
    import OpenSSL
except ImportError:
    OpenSSL = None

URLFETCH_TIMEOUT = 55
clientPort = 9090



class bridge2gae_recv(threading.Thread):
    def __init__(self, bridgesock, clientsock):
        threading.Thread.__init__(self)
        self.bridgesock = bridgesock
        self.clientsock = clientsock

    def run(self):
    	try:
    		curtime = time.time()
    		while True:
    			if (time.time() - curtime) > URLFETCH_TIMEOUT:
    				break
    			requestdata = None
    			(ins, _, errors) = select.select([self.clientsock], [], [self.clientsock], 2)
    			if errors:
    				logging.info('client sock error')
    				break
    			if self.clientsock in ins:
    				requestdata = self.clientsock.recv(4096)
    			if requestdata and self.bridgesock:
    				self.bridgesock.sendall(requestdata)
    			else:
    				continue
    	except socket.error as e:
    		logging.info('bridge to gae ,socket.error')
    		
class client2gae_recv(threading.Thread):
    def __init__(self, bridgesock, clientsock):
        threading.Thread.__init__(self)
        self.bridgesock = bridgesock
        self.clientsock = clientsock

    def run(self):
    	try:
    		curtime = time.time()
    		while True:
    			if (time.time() - curtime) > URLFETCH_TIMEOUT:
    				self.clientsock.sendall('**********************end-gtor*************************')
    				break
    			reponsedata = None
    			(ins, _, errors) = select.select([self.bridgesock], [], [self.bridgesock], 2)
    			if errors:
    				logging.info('bridgesock sock error')
    				break
    			if self.bridgesock in ins:
    				reponsedata = self.bridgesock.recv(4096)
    			if reponsedata and self.clientsock:
    				self.clientsock.sendall(reponsedata)
    			else:
    				continue
    	except socket.error as e:
    		logging.info('client to gae,socket.error')


def gae_application(environ, start_response):
    if environ['REQUEST_METHOD'] == 'GET':
        if '204' in environ['QUERY_STRING']:
            start_response('204 No Content', [])
            yield ''
        else:
            timestamp = long(os.environ['CURRENT_VERSION_ID'].split('.')[1])/2**28
            ctime = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp+8*3600))
            html = u'Gtor Python Server %s \u5df2\u7ecf\u5728\u5de5\u4f5c\u4e86\uff0c\u90e8\u7f72\u65f6\u95f4 %s\n' % (__version__, ctime)
            start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
            yield html.encode('utf8')
        raise StopIteration
    
    wsgi_input = environ['wsgi.input']
    httpslen = wsgi_input.read(2)
    metadata_length, = struct.unpack('!h', httpslen)
    metadata = wsgi_input.read(metadata_length)
    metadata = zlib.decompress(metadata, -zlib.MAX_WBITS)
    headers = dict(x.split(':', 1) for x in metadata.splitlines() if x)
    method = headers.pop('G-Method')
    url = headers.pop('G-Url')

    bridgeIP, _, bridgePort = url.rpartition(':')
    bridgePort = int(bridgePort)
    clientIP = environ['REMOTE_ADDR']
    
    flag = 1
    bridgesock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    if method == 'CONNECT':
    	try:		
    		bridgesock.connect((bridgeIP, bridgePort))
    	except:	
    		logging.info('*connect to tor node error.')
    		flag = 0
    	try:
    		clientsock.connect((clientIP,int(clientPort)))  		
    	except:	
    		logging.info('connect to client error.')
    		flag = 0
    
    if flag:
    	bridge2gae_recv_thread = bridge2gae_recv(bridgesock, clientsock)
    	bridge2gae_recv_thread.start()
    	client2gae_recv_thread = client2gae_recv(bridgesock, clientsock)
    	client2gae_recv_thread.start()
    	
    	bridge2gae_recv_thread.join()
    	client2gae_recv_thread.join()
    
    if bridgesock:
    	bridgesock.close()
    if clientsock:
    	clientsock.close()

app = gae_application
application = app if sae is None else sae.create_wsgi_app(app)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - - %(asctime)s %(message)s', datefmt='[%b %d %H:%M:%S]')
    import gevent
    import gevent.server
    import gevent.wsgi
    import gevent.monkey
    gevent.monkey.patch_all(dns=gevent.version_info[0] >= 1)
    server = gevent.wsgi.WSGIServer(('', int(sys.argv[1])), application)
    server.serve_forever()

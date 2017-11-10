import logging

FORMAT = '%(asctime)s (%(threadName)-2s) %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
LOG = logging.getLogger()

from sessionClass import *
import sessionClass as sc
from serverMain import *
from threading import Thread, Lock, currentThread

from socket import AF_INET, SOCK_STREAM, socket
from socket import error as soc_err

import os, sys, inspect

sys.path.insert(1, os.path.join(sys.path[0], '..'))
from messageProtocol import *


class clientHandler(Thread):
    def __init__(self, soc, Server):
        LOG.info('Created client %s:%d' % soc.getsockname())
        Thread.__init__(self)
        self.soc = soc  # tuple (IP, port)
        self.score = 0
        self.nickname = None
        self.session = None
        self.Server = Server
        self.send_lock = Lock()

    def getNickname(self):
        return self.nickname

    def getScoreNickname(self):
        return self.nickname + ' ' + str(self.score)

    def incScore(self):
        self.score += 1

    def decScore(self):
        self.score -= 1

    def requestPutNumber(self, unparsedInts):
        LOG.debug('Client %s:%d wants to write to sudoku: %s' \
                  '' % (self.soc.getsockname() + (unparsedInts,)))
        try:
            ints = list(unparsedInts)
            x, y, number = int(ints[0]), int(ints[1]), int(ints[2])
            for n in [x,y,number]:
                if n not in range(1,10):
                    REP, MSG = REP_NOT_OK, "nr not in 1...9"
            REP, MSG = self.session.putNumber(x, y, number, self)
        except:
            REP, MSG = REP_NOT_OK, "Parsing int failed"
        return REP, MSG

    def rcvMessage(self):
        m, b = '', ''
        try:
            b = self.soc.recv(1)
            m += b
            while len(b) > 0 and not (b.endswith(MSG_TERMCHR)):
                b = self.soc.recv(1)
                m += b

            if len(b) <= 0:
                LOG.info('Client %s:%d disconnected' % \
                         self.soc.getsockname())
                self.soc.close()
                m = ''
            m = m[:-1]
        except KeyboardInterrupt:
            self.soc.close()
            LOG.info('Ctrl+C issued, disconnecting client %s:%d' \
                     % self.soc.getsockname())
            m = ''
        except soc_err as e:
            if e.errno == 107:
                LOG.warn('Client %s:%d left before server could handle it'
                         % self.soc.getsockname())
            else:
                LOG.error('Error: %s' % str(e))
            self.soc.close()
            LOG.info('Client %s:%d disconnected' % self.soc.getsockname())
            m = ''
        return m

    def joinSession(self, sessName):
        for sess in self.Server.sessionList:
            if sessName == sess.sessName:
                if sess.addMe(self):
                    self.session = sess
                    if self.session.gameRunning:
                        return "Start"
                    return 'Wait'
                return "session full"
        return "No such session"

    def createSession(self, sessName, maxPlayerCount):
        if sessName in self.Server.getSessNames():
            return REP_NOT_OK, "Session name in use"
        if maxPlayerCount < 2:
            return REP_NOT_OK, "Too few max players specified %d" % maxPlayerCount
        sess = sc.sessionClass(sessName, maxPlayerCount, self.Server)
        self.Server.sessionList.append(sess)
        self.session = sess
        if sess.addMe(self):
            self.session = sess
            return "OK", ""
        return REP_NOT_OK, "session full"

    def rcvProtocolMessage(self, message):
        REP, MSG = 'OK', ''

        LOG.debug('Received request [%d bytes] in total' % len(message))
        if len(message) < 2:
            LOG.debug('Not enough data received from %s ' % message)
            return REP_NOT_OK, 'received too short message'
        elif message.count(HEADER_SEP, 2) > 0 or message.count(FIELD_SEP) > 1:
            LOG.debug('Faulty message received from %s ' % message)
            return REP_NOT_OK, 'received too faulty message'
        payload = message[2:]

        if message.startswith(REQ_NICKNAME + HEADER_SEP):
            if payload not in self.Server.getUsedNicknames():
                self.nickname = payload
                LOG.debug('Client %s:%d will use name ' \
                          '%s' % (self.soc.getsockname() + (self.nickname,)))
                REP = REP_CURRENT_SESSIONS
                MSG = ''
                self.send_notification('Available Sessions: %s' \
                            % ''.join(map(lambda x: '\n  ' + \
                            x.getSessInfo(), self.Server.getSessions())))
            else:
                REP, MSG = REP_NOT_OK, "Name in use"

        elif message.startswith(REQ_JOIN_EXIST_SESS + HEADER_SEP):
            if (self.name == None):
                LOG.debug('Name unknown at session join: %s ' % message)
                REP, MSG = REP_NOT_OK, "Specify name"
            elif (self.session != None):
                LOG.debug('Join session while in session: %s ' % message)
                REP, MSG = REP_NOT_OK, "Leave current session"
            else:
                msg = self.joinSession(payload)
            if msg == "Wait":
                LOG.debug('Client %s:%d joined session ' \
                          '%s' % (self.soc.getsockname() + (payload,)))
                REP, MSG = REP_WAITING_PLAYERS, ''
            elif msg == "Start":
                LOG.debug('Client %s:%d joined session ' \
                          '%s' % (self.soc.getsockname() + (payload,)))
                REP, MSG = None, ''
            else:
                LOG.debug('Client %s:%d failed to join session: ' \
                          '%s' % (self.soc.getsockname() + (msg,)))
                REP, MSG = REP_NOT_OK, msg

        elif message.startswith(REQ_JOIN_NEW_SESS + HEADER_SEP):
            try:
                if self.name == None:
                    LOG.debug('Name unknown at session create: %s ' % message)
                    REP, MSG = REP_NOT_OK, "Specify name"
                elif self.session != None:
                    LOG.debug('Join session while in session: %s ' % message)
                    REP, MSG = REP_NOT_OK, "Leave current session"
                else:
                    sessname, playercount = payload.split(FIELD_SEP)
                    playercount = int(playercount)
                    REP, MSG = self.createSession(sessname, playercount)
                    if REP == "OK":
                        LOG.debug('Client %s:%d created session %s' \
                                  % (self.soc.getsockname() + (sessname,)))
                        REP, MSG = REP_WAITING_PLAYERS, ''
                    else:
                        LOG.debug('Client %s:%d failed to create and join session: ' \
                                  '%s' % (self.soc.getsockname() + (MSG,)))
            except:
                REP, MSG = REP_NOT_OK, "Unable to parse integer"

        elif message.startswith(REQ_PUT_NR + HEADER_SEP):
            if self.session == None:
                LOG.debug('Not in session: %s ' % message)
                REP, MSG = REP_NOT_OK, "Not in session"
            else:
                REP, MSG = self.requestPutNumber(payload)

        else:
            LOG.debug('Unknown control message received: %s ' % message)
            REP, MSG = REP_NOT_OK, "Unknown control message"

        return REP, MSG


    def session_send(self, msg):
        m = msg + MSG_TERMCHR
        LOG.info('Send to %s : %s' % (self.nickname, m))
        with self.send_lock:
            r = False
            try:
                self.soc.sendall(m)
                r = True
            except KeyboardInterrupt:
                self.soc.close()
                LOG.info('Ctrl+C issued, disconnecting client %s:%d' \
                         '' % self.soc.getsockname())
            except soc_err as e:
                if e.errno == 107:
                    LOG.warn('Client %s left before server could handle it' \
                             '' % self.soc.nickname)
                else:
                    LOG.error('Error: %s' % str(e))
                self.soc.close()
                LOG.info('Client %s:%d disconnected' % self.soc.getsockname())
            return r

    def send_notification(self, message):
        return self.session_send(REP_NOTIFY + HEADER_SEP + message)

    def send_specific(self, header, message):
        return self.session_send(header + HEADER_SEP + message)

    def run(self):
        while 1:
            m = self.rcvMessage()
            LOG.debug('Raw msg: %s' % m)
            if len(m) <= 0:
                break
            rsp, msg = self.rcvProtocolMessage(m)
            if rsp == None: continue
            if not self.send_specific(rsp, msg):
                break
        self.exists = False
        if self.session != None:
            self.session.removeMe()
        self.Server.removeMe()

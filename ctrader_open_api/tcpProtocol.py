#!/usr/bin/env python

from collections import deque
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet import task
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage, ProtoHeartbeatEvent
import datetime

class TcpProtocol(Int32StringReceiver):
    MAX_LENGTH = 15000000
    _send_queue = deque([])
    _send_task = None
    _lastSendMessageTime = None

    def connectionMade(self):
        print('$TcpProtocol connectionMade')
        super().connectionMade()

        if not self._send_task:
            self._send_task = task.LoopingCall(self._sendStrings)
        self._send_task.start(1)
        self.factory.connected(self)

    def connectionLost(self, reason):
        print('$TcpProtocol connectionLost')
        super().connectionLost(reason)
        if self._send_task.running:
            self._send_task.stop()
        self.factory.disconnected(reason)

    def heartbeat(self):
        print('$TcpProtocol heartbeat')
        self.send(ProtoHeartbeatEvent(), True)

    def send(self, message, instant=False, clientMsgId=None, isCanceled = None):
        print('$TcpProtocol send')
        data = b''

        if isinstance(message, ProtoMessage):
            data = message.SerializeToString()

        if isinstance(message, bytes):
            data = message

        if isinstance(message, ProtoMessage.__base__):

            ###

            msg = ProtoMessage(payload=message.SerializeToString(),
                               clientMsgId=clientMsgId,
                               payloadType=message.payloadType)
            data = msg.SerializeToString()

        print(f'protocol _send data: {data}')

        if instant:
            self.sendString(data)
            self._lastSendMessageTime = datetime.datetime.now()
        else:
            self._send_queue.append((isCanceled, data))

    def _sendStrings(self):
        print('$TcpProtocol _sendStrings')
        size = len(self._send_queue)

        if not size:
            if self._lastSendMessageTime is None or (datetime.datetime.now() - self._lastSendMessageTime).total_seconds() > 20:
                self.heartbeat()
            return

        for _ in range(min(size, self.factory.numberOfMessagesToSendPerSecond)):
            isCanceled, data = self._send_queue.popleft()
            if isCanceled is not None and isCanceled():
                continue;
            self.sendString(data)
        self._lastSendMessageTime = datetime.datetime.now()

    def stringReceived(self, data):
        print('$TcpProtocol stringReceived')
        print(f'data: {data}')

        msg = ProtoMessage()
        msg.ParseFromString(data)

        if msg.payloadType == ProtoHeartbeatEvent().payloadType:
            self.heartbeat()
        self.factory.received(msg)
        return data

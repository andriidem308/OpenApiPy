import asyncio
import datetime
from collections import deque

from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage, ProtoHeartbeatEvent


class TcpProtocol(asyncio.Protocol):
    MAX_LENGTH = 15000000

    def __init__(self, client):
        print('$TcpProtocol __init__')
        self.client = client
        self.transport = None
        self._send_queue = deque([])
        self._send_task = None
        self._last_send_message_time = None

    def connection_made(self, transport):
        print('$TcpProtocol connection_made')
        # print(f'transport: {transport}')

        self.transport = transport
        self._send_task = asyncio.create_task(self._send_strings())
        asyncio.create_task(self.client.connected(self))

    def connection_lost(self, exc):
        print('$TcpProtocol connection_lost')

        self._send_task.cancel()
        asyncio.create_task(self.client.disconnected(exc))

    def heartbeat(self):
        print('$TcpProtocol heartbeat')
        self.send(ProtoHeartbeatEvent(), True)

    def send(self, message, instant=False, clientMsgId=None, is_canceled=None):
        print('$TcpProtocol send')

        data = b''

        if isinstance(message, ProtoMessage):
            data = message.SerializeToString()

        if isinstance(message, bytes):
            data = message

        if isinstance(message, ProtoMessage.__base__):
            msg = ProtoMessage(payload=message.SerializeToString(),
                               clientMsgId=clientMsgId,
                               payloadType=message.payloadType)
            data = msg.SerializeToString()

        print(f'protocol _send data: {data}')

        if instant:
            self.transport.write(data)
            self._last_send_message_time = datetime.datetime.now()
        else:
            self._send_queue.append((is_canceled, data))

    async def _send_strings(self):
        print('$TcpProtocol _send_strings')

        while True:
            if not self._send_queue:
                if self._last_send_message_time is None or (
                    datetime.datetime.now() - self._last_send_message_time).total_seconds() > 20:
                    self.heartbeat()
                await asyncio.sleep(1)
                continue

            for _ in range(min(len(self._send_queue), self.client.number_of_messages_to_send_per_second)):
                is_canceled, data = self._send_queue.popleft()
                if is_canceled is not None and is_canceled():
                    continue
                self.transport.write(data)
            self._last_send_message_time = datetime.datetime.now()
            await asyncio.sleep(1)

    def data_received(self, data):
        print('$TcpProtocol data_received')

        msg = ProtoMessage()
        msg.ParseFromString(data)

        if msg.payloadType == ProtoHeartbeatEvent().payloadType:
            self.heartbeat()

        asyncio.create_task(self.client.received(msg))

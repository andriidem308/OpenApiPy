from ctrader_open_api import Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *


import datetime
from collections import deque

from inputimeout import inputimeout
import asyncio

from ctrader_open_api.endpoints import EndPoints


class TcpProtocol(asyncio.Protocol):
    MAX_LENGTH = 15000000

    def __init__(self, client, loop):
        self._send_queue = deque()
        self._send_task = None
        self._lastSendMessageTime = None
        self.client = client
        self.loop = loop
        self.transport = None
        self.buffer = b''
        self.msg_length = None

    def connection_made(self, transport):
        super().connection_made(transport)
        if not self._send_task:
            self._send_task = self.loop.create_task(self._send_strings())
        self.client.connected(self)

    def connection_lost(self, exc):
        if self._send_task:
            self._send_task.cancel()
        self.client.disconnected(exc)

    def heartbeat(self):
        self.send(ProtoHeartbeatEvent(), True)

    def send(self, message, instant=False, clientMsgId=None, isCanceled=None):
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
            self._lastSendMessageTime = datetime.datetime.now()
        else:
            print(f'self._send_queue: {self._send_queue}')
            self._send_queue.append((isCanceled, data))
            print(f'self._send_queue appended: {self._send_queue}')

    async def _send_strings(self):
        while True:
            size = len(self._send_queue)
            if not size:
                if self._lastSendMessageTime is None or (
                    datetime.datetime.now() - self._lastSendMessageTime).total_seconds() > 20:
                    self.heartbeat()
                await asyncio.sleep(1)
                continue

            for _ in range(min(size, self.client.numberOfMessagesToSendPerSecond)):
                isCanceled, data = self._send_queue.popleft()
                if isCanceled is not None and isCanceled():
                    continue
                self.transport.write(data)
            self._lastSendMessageTime = datetime.datetime.now()
            await asyncio.sleep(1)


    def string_received(self, data):
        print(f'data: {data}')

        msg = ProtoMessage()  # Create an instance of your protobuf message class
        msg.ParseFromString(data)

        if msg.payloadType == ProtoHeartbeatEvent().payloadType:
            self.heartbeat()
        self.factory.received(msg)


    def data_received(self, data):
        import struct
        self.buffer += data
        while True:
            if self.msg_length is None:
                if len(self.buffer) >= 4:
                    self.msg_length = struct.unpack('!I', self.buffer[:4])[0]
                    self.buffer = self.buffer[4:]
                else:
                    break
            if self.msg_length is not None:
                if len(self.buffer) >= self.msg_length:
                    msg = self.buffer[:self.msg_length]
                    self.buffer = self.buffer[self.msg_length:]
                    self.msg_length = None
                    self.string_received(msg)
                else:
                    break


class Client:
    def __init__(self, host: str, port: int, protocol_factory: TcpProtocol, loop: asyncio.AbstractEventLoop, numberOfMessagesToSendPerSecond: int = 5):
        self.loop = loop
        self.numberOfMessagesToSendPerSecond = numberOfMessagesToSendPerSecond
        self._events = dict()
        self._response_futures = dict()
        self.isConnected = False

        self._protocol_factory: TcpProtocol = protocol_factory(self, loop)
        coro = loop.create_connection(lambda: self._protocol_factory, host, port)
        self._connection = loop.run_until_complete(coro)

    def connected(self, protocol):
        self.isConnected = True
        if hasattr(self, "_connectedCallback"):
            self._connectedCallback(self)

    def disconnected(self, reason):
        self.isConnected = False
        self._response_futures.clear()
        if hasattr(self, "_disconnectedCallback"):
            self._disconnectedCallback(self, reason)

    def received(self, message):
        if hasattr(self, "_messageReceivedCallback"):
            self._messageReceivedCallback(self, message)
        if message.clientMsgId is not None and message.clientMsgId in self._response_futures:
            future = self._response_futures.pop(message.clientMsgId)
            future.set_result(message)

    async def send(self, message, clientMsgId=None, responseTimeoutInSeconds=5, **params):
        if type(message) in [str, int]:
            message = Protobuf.get(message, **params)

        response_future = self.loop.create_future()
        if clientMsgId is None:
            clientMsgId = str(id(response_future))

        self._response_futures[clientMsgId] = response_future

        try:
            await self._send_message(message, clientMsgId)

            if response_future.done():
                response = response_future.result()  # Get the result if available
            else:
                response = await asyncio.wait_for(response_future, timeout=responseTimeoutInSeconds)

            print(f'client send response: {response}')
        except asyncio.TimeoutError:
            self._on_response_failure(clientMsgId)
            print(f'TimeoutError: {response}')
            raise
        finally:
            print('aboba')
            self._response_futures.pop(clientMsgId, None)

        return response

    async def _send_message(self, message, clientMsgId):
        protocol = self._protocol_factory
        protocol.send(message, clientMsgId=clientMsgId, isCanceled=lambda: clientMsgId not in self._response_futures)
        self._response_futures[clientMsgId].set_result("Message sent successfully")

    def _on_response_failure(self, clientMsgId):
        if clientMsgId in self._response_futures:
            future = self._response_futures.pop(clientMsgId)
            future.set_exception(asyncio.TimeoutError())

    def _timeout_response(self, clientMsgId):
        if clientMsgId in self._response_futures:
            response_futures = self._response_futures.pop(clientMsgId)
            self.loop.call_soon_threadsafe(response_futures.set_exception, asyncio.TimeoutError())

    def setConnectedCallback(self, callback):
        self._connectedCallback = callback

    def setDisconnectedCallback(self, callback):
        self._disconnectedCallback = callback

    def setMessageReceivedCallback(self, callback):
        self._messageReceivedCallback = callback


if __name__ == "__main__":
    currentAccountId = 26213142
    hostType = 'demo'

    while hostType != "live" and hostType != "demo":
        print(f"{hostType} is not a valid host type.")
        hostType = input("Host (Live/Demo): ")

    appClientId = '5914_LRMBD0LJWuue78FqcOxTADdXpOqjDrrphnZiyUjCJC3yEqGlaM'
    appClientSecret = 'm5IDK3v7iJnJcDHvo4RJjnyRv7CHEun5VjR57K4zQ8YLDcjTCJ'
    accessToken = '5buBFoMeswX8jCd-4URRkWCjBA4Jg_2sGtEZL25kMAY'

    loop = asyncio.get_event_loop()
    client = Client(EndPoints.PROTOBUF_LIVE_HOST if hostType.lower() == "live" else EndPoints.PROTOBUF_DEMO_HOST,
                    EndPoints.PROTOBUF_PORT, TcpProtocol, loop)


    async def connected(client: Client):  # Callback for client connection
        print("\nConnected")
        request = ProtoOAApplicationAuthReq()
        request.clientId = appClientId
        request.clientSecret = appClientSecret

        print(f'connected request: {request}')

        try:
            await client.send(request)
            print('message sent!')
            print('executing user command')
            await executeUserCommand()
        except Exception as e:
            await onError(e)


    async def disconnected(client, reason):
        print("\nDisconnected: ", reason)


    async def onMessageReceived(client, message):
        if message.payloadType in [ProtoOASubscribeSpotsRes().payloadType, ProtoOAAccountLogoutRes().payloadType,
                                   ProtoHeartbeatEvent().payloadType]:
            return
        elif message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            print("API Application authorized\n")
            print(
                "Please use setAccount command to set the authorized account before sending any other command, try help for more detail\n")
            print("To get account IDs use ProtoOAGetAccountListByAccessTokenReq command")
            if currentAccountId is not None:
                sendProtoOAAccountAuthReq()
                return
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            protoOAAccountAuthRes = Protobuf.extract(message)
            print(f"Account {protoOAAccountAuthRes.ctidTraderAccountId} has been authorized\n")
            print("This acccount will be used for all future requests\n")
            print("You can change the account by using setAccount command")
        else:
            print("Message received: \n", Protobuf.extract(message))

        await asyncio.sleep(3)
        await executeUserCommand()


    async def onError(exception):
        print("Message Error: ", exception)
        await asyncio.sleep(3)
        await executeUserCommand()


    async def executeUserCommand():
        userInput = input("Command (ex help): ")
        # userInput = await inputimeout("Command (ex help): ", timeout=18)
        print(f'userInput: {userInput}')

        if userInput == 'stop':
            await disconnected(client, 'manual')
        else:
            print("Invalid Command: ", userInput)
            await asyncio.sleep(3)
            await executeUserCommand()


    client.setConnectedCallback(connected)
    client.setDisconnectedCallback(disconnected)
    client.setMessageReceivedCallback(onMessageReceived)

    # req = ProtoOAApplicationAuthReq()
    # req.clientId = appClientId
    # req.clientSecret = appClientSecret

    request = ProtoOAApplicationAuthReq()
    request.clientId = appClientId
    request.clientSecret = appClientSecret

    loop.run_until_complete(client.send(request))
    print('chcks')
    loop.run_forever()

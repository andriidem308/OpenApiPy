import asyncio
from collections import deque
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoMessage, ProtoHeartbeatEvent
import datetime

class TcpProtocol(asyncio.Protocol):
    MAX_LENGTH = 15000000

    def __init__(self, client):
        self.client = client
        self._send_queue = deque([])
        self._lastSendMessageTime = None
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport
        self.client._connected(self)
        self._send_task = asyncio.create_task(self._send_strings())

    def connection_lost(self, exc):
        self.client._disconnected(exc)
        if self._send_task:
            self._send_task.cancel()

    def data_received(self, data):
        message = ProtoMessage()
        message.ParseFromString(data)
        asyncio.create_task(self.client._received(message))

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

        if instant:
            self._transport.write(data)
            self._lastSendMessageTime = datetime.datetime.now()
        else:
            self._send_queue.append((isCanceled, data))

    async def _send_strings(self):
        try:
            while True:
                size = len(self._send_queue)
                if not size:
                    if self._lastSendMessageTime is None or (datetime.datetime.now() - self._lastSendMessageTime).total_seconds() > 20:
                        self.heartbeat()
                    await asyncio.sleep(1)
                    continue

                for _ in range(min(size, self.client.numberOfMessagesToSendPerSecond)):
                    isCanceled, data = self._send_queue.popleft()
                    if isCanceled is not None and isCanceled():
                        continue
                    self._transport.write(data)
                self._lastSendMessageTime = datetime.datetime.now()
                await asyncio.sleep(1 / self.client.numberOfMessagesToSendPerSecond)
        except asyncio.CancelledError:
            pass

    def heartbeat(self):
        self.send(ProtoHeartbeatEvent(), True)

class Client:
    def __init__(self, host, port, numberOfMessagesToSendPerSecond=5):
        self.host = host
        self.port = port
        self.numberOfMessagesToSendPerSecond = numberOfMessagesToSendPerSecond
        self._events = dict()
        self._responseDeferreds = dict()
        self.isConnected = False

    async def connect(self):
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_connection(
            lambda: TcpProtocol(self), self.host, self.port
        )
        self.protocol = protocol

    async def _connected(self, protocol):
        self.isConnected = True
        if hasattr(self, "_connectedCallback"):
            await self._connectedCallback(self)

    async def _disconnected(self, reason):
        self.isConnected = False
        self._responseDeferreds.clear()
        if hasattr(self, "_disconnectedCallback"):
            await self._disconnectedCallback(self, reason)

    async def _received(self, message):
        if hasattr(self, "_messageReceivedCallback"):
            await self._messageReceivedCallback(self, message)
        if message.clientMsgId and message.clientMsgId in self._responseDeferreds:
            responseDeferred = self._responseDeferreds.pop(message.clientMsgId)
            responseDeferred.set_result(message)

    def send(self, message, clientMsgId=None, responseTimeoutInSeconds=5, **params):
        responseDeferred = asyncio.Future()
        if clientMsgId is None:
            clientMsgId = str(id(responseDeferred))
        if clientMsgId is not None:
            self._responseDeferreds[clientMsgId] = responseDeferred
        responseDeferred.add_done_callback(lambda fut: self._onResponseFailure(fut, clientMsgId) if fut.exception() else None)
        responseDeferred.add_timeout(responseTimeoutInSeconds)
        asyncio.create_task(self.protocol.send(message, clientMsgId=clientMsgId, isCanceled=lambda: clientMsgId not in self._responseDeferreds))
        return responseDeferred

    def setConnectedCallback(self, callback):
        self._connectedCallback = callback

    def setDisconnectedCallback(self, callback):
        self._disconnectedCallback = callback

    def setMessageReceivedCallback(self, callback):
        self._messageReceivedCallback = callback

    def _onResponseFailure(self, future, msgId):
        if msgId in self._responseDeferreds:
            del self._responseDeferreds[msgId]

if __name__ == "__main__":
    currentAccountId = 26213142
    hostType = 'demo'

    appClientId = '5914_LRMBD0LJWuue78FqcOxTADdXpOqjDrrphnZiyUjCJC3yEqGlaM'
    appClientSecret = 'm5IDK3v7iJnJcDHvo4RJjnyRv7CHEun5VjR57K4zQ8YLDcjTCJ'
    accessToken = '5buBFoMeswX8jCd-4URRkWCjBA4Jg_2sGtEZL25kMAY'

    async def connected(client):
        print("\nConnected")
        request = ProtoOAApplicationAuthReq()
        request.clientId = appClientId
        request.clientSecret = appClientSecret
        deferred = client.send(request)
        deferred.add_done_callback(lambda fut: onError(fut.exception()) if fut.exception() else None)

    async def disconnected(client, reason):
        print("\nDisconnected: ", reason)

    async def onMessageReceived(client, message):
        if message.payloadType in [ProtoOASubscribeSpotsRes().payloadType, ProtoOAAccountLogoutRes().payloadType, ProtoHeartbeatEvent().payloadType]:
            return
        elif message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            print("API Application authorized\n")
            print("Please use setAccount command to set the authorized account before sending any other command, try help for more detail\n")
            print("To get account IDs use ProtoOAGetAccountListByAccessTokenReq command")
            if currentAccountId is not None:
                await sendProtoOAAccountAuthReq(client)
                return
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            protoOAAccountAuthRes = Protobuf.extract(message)
            print(f"Account {protoOAAccountAuthRes.ctidTraderAccountId} has been authorized\n")
            print("This account will be used for all future requests\n")
            print("You can change the account by using setAccount command")
        else:
            print("Message received: \n", Protobuf.extract(message))
        await asyncio.sleep(3)
        await executeUserCommand()

    async def onError(failure):
        print("Message Error: ", failure)
        await asyncio.sleep(3)
        await executeUserCommand()

    async def showHelp():
        print("Commands (Parameters with an * are required), ignore the description inside ()")
        print("setAccount(For all subsequent requests this account will be used) *accountId")
        await asyncio.sleep(3)
        await executeUserCommand()

    async def setAccount(accountId):
        global currentAccountId
        if currentAccountId is not None:
            await sendProtoOAAccountLogoutReq()
        currentAccountId = int(accountId)
        await sendProtoOAAccountAuthReq()

    async def sendProtoOAAccountLogoutReq(clientMsgId=None):
        request = ProtoOAAccountLogoutReq()
        request.ctidTraderAccountId = currentAccountId
        deferred = client.send(request, clientMsgId=clientMsgId)
        deferred.add_done_callback(lambda fut: onError(fut.exception()) if fut.exception() else None)

    async def sendProtoOAAccountAuthReq(clientMsgId=None):
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = currentAccountId
        request.accessToken = accessToken
        deferred = client.send(request, clientMsgId=clientMsgId)
        deferred.add_done_callback(lambda fut: onError(fut.exception()) if fut.exception() else None)

    commands = {
        "help": showHelp,
        "setAccount": setAccount,
    }

    async def executeUserCommand():
        try:
            print("\n")
            userInput = input("Command (ex help): ")
        except Exception as e:
            print("Command Input Error:", e)
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        userInputSplit = userInput.split(" ")
        if not userInputSplit:
            print("Command split error: ", userInput)
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        command = userInputSplit[0]
        try:
            parameters = [parameter if parameter[0] != "*" else parameter[1:] for parameter in userInputSplit[1:]]
        except Exception as e:
            print("Invalid parameters: ", userInput, e)
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        if command in commands:
            await commands[command]

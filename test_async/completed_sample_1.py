#!/usr/bin/env python

import datetime
from collections import deque

from inputimeout import inputimeout, TimeoutOccurred
from twisted.application.internet import ClientService
from twisted.internet import task, reactor, defer
from twisted.internet.endpoints import clientFromString
from twisted.internet.protocol import ClientFactory
from twisted.protocols.basic import Int32StringReceiver

from ctrader_open_api.endpoints import EndPoints
from ctrader_open_api.protobuf import Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *


class Factory(ClientFactory):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.client = kwargs['client']
        self.numberOfMessagesToSendPerSecond = self.client.numberOfMessagesToSendPerSecond

    def connected(self, protocol):
        self.client._connected(protocol)

    def disconnected(self, reason):
        self.client._disconnected(reason)

    def received(self, message):
        self.client._received(message)


class TcpProtocol(Int32StringReceiver):
    MAX_LENGTH = 15000000
    _send_queue = deque([])
    _send_task = None
    _lastSendMessageTime = None

    def connectionMade(self):
        super().connectionMade()

        if not self._send_task:
            self._send_task = task.LoopingCall(self._sendStrings)
        self._send_task.start(1)
        self.factory.connected(self)

    def connectionLost(self, reason):
        super().connectionLost(reason)
        if self._send_task.running:
            self._send_task.stop()
        self.factory.disconnected(reason)

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
            self.sendString(data)
            self._lastSendMessageTime = datetime.datetime.now()
        else:
            print(f'self._send_queue: {self._send_queue}')
            self._send_queue.append((isCanceled, data))
            print(f'self._send_queue appended: {self._send_queue}')

    def _sendStrings(self):
        size = len(self._send_queue)

        if not size:
            if self._lastSendMessageTime is None or (
                datetime.datetime.now() - self._lastSendMessageTime).total_seconds() > 20:
                self.heartbeat()
            return

        for _ in range(min(size, self.factory.numberOfMessagesToSendPerSecond)):
            isCanceled, data = self._send_queue.popleft()
            if isCanceled is not None and isCanceled():
                continue;
            self.sendString(data)
        self._lastSendMessageTime = datetime.datetime.now()

    def stringReceived(self, data):
        msg = ProtoMessage()
        msg.ParseFromString(data)

        if msg.payloadType == ProtoHeartbeatEvent().payloadType:
            self.heartbeat()
        self.factory.received(msg)
        return data


class Client(ClientService):
    def __init__(self, host, port, protocol, retryPolicy=None, clock=None, prepareConnection=None,
                 numberOfMessagesToSendPerSecond=5):
        self._runningReactor = reactor
        self.numberOfMessagesToSendPerSecond = numberOfMessagesToSendPerSecond
        endpoint = clientFromString(self._runningReactor, f"ssl:{host}:{port}")
        factory = Factory.forProtocol(protocol, client=self)
        super().__init__(endpoint, factory, retryPolicy=retryPolicy, clock=clock, prepareConnection=prepareConnection)
        self._events = dict()
        self._responseDeferreds = dict()
        self.isConnected = False

    def startService(self):
        if self.running:
            return
        ClientService.startService(self)

    def stopService(self):
        if self.running and self.isConnected:
            ClientService.stopService(self)

    def _connected(self, protocol):
        self.isConnected = True
        if hasattr(self, "_connectedCallback"):
            self._connectedCallback(self)

    def _disconnected(self, reason):
        self.isConnected = False
        self._responseDeferreds.clear()
        if hasattr(self, "_disconnectedCallback"):
            self._disconnectedCallback(self, reason)

    def _received(self, message):
        if hasattr(self, "_messageReceivedCallback"):
            self._messageReceivedCallback(self, message)
        if (message.clientMsgId is not None and message.clientMsgId in self._responseDeferreds):
            responseDeferred = self._responseDeferreds[message.clientMsgId]
            self._responseDeferreds.pop(message.clientMsgId)
            responseDeferred.callback(message)

    def send(self, message, clientMsgId=None, responseTimeoutInSeconds=5, **params):
        if type(message) in [str, int]:
            message = Protobuf.get(message, **params)
        responseDeferred = defer.Deferred(self._cancelMessageDiferred)
        if clientMsgId is None:
            clientMsgId = str(id(responseDeferred))
        if clientMsgId is not None:
            self._responseDeferreds[clientMsgId] = responseDeferred

        responseDeferred.addErrback(lambda failure: self._onResponseFailure(failure, clientMsgId))
        responseDeferred.addTimeout(responseTimeoutInSeconds, self._runningReactor)
        protocolDiferred = self.whenConnected(failAfterFailures=1)
        protocolDiferred.addCallbacks(lambda protocol: protocol.send(message, clientMsgId=clientMsgId,
                                                                     isCanceled=lambda: clientMsgId not in self._responseDeferreds),
                                      responseDeferred.errback)
        return responseDeferred

    def setConnectedCallback(self, callback):
        self._connectedCallback = callback

    def setDisconnectedCallback(self, callback):
        self._disconnectedCallback = callback

    def setMessageReceivedCallback(self, callback):
        self._messageReceivedCallback = callback

    def _onResponseFailure(self, failure, msgId):
        if (msgId is not None and msgId in self._responseDeferreds):
            self._responseDeferreds.pop(msgId)
        return failure

    def _cancelMessageDiferred(self, deferred):
        deferredIdString = str(id(deferred))
        if (deferredIdString in self._responseDeferreds):
            self._responseDeferreds.pop(deferredIdString)


if __name__ == "__main__":
    currentAccountId = 26213142
    hostType = 'demo'

    appClientId = '5914_LRMBD0LJWuue78FqcOxTADdXpOqjDrrphnZiyUjCJC3yEqGlaM'
    appClientSecret = 'm5IDK3v7iJnJcDHvo4RJjnyRv7CHEun5VjR57K4zQ8YLDcjTCJ'
    accessToken = '5buBFoMeswX8jCd-4URRkWCjBA4Jg_2sGtEZL25kMAY'

    client = Client(EndPoints.PROTOBUF_LIVE_HOST if hostType.lower() == "live" else EndPoints.PROTOBUF_DEMO_HOST,
                    EndPoints.PROTOBUF_PORT, TcpProtocol)


    def connected(client: Client):  # Callback for client connection
        print("\nConnected")
        request = ProtoOAApplicationAuthReq()
        request.clientId = appClientId
        request.clientSecret = appClientSecret
        print(f'connected request: {request}')
        deferred = client.send(request)
        deferred.addErrback(onError)


    def disconnected(client, reason):  # Callback for client disconnection
        print("\nDisconnected: ", reason)


    def onMessageReceived(client, message):  # Callback for receiving all messages
        # if message.payloadType in [ProtoOASubscribeSpotsRes().payloadType, ProtoOAAccountLogoutRes().payloadType,
        #                            ProtoHeartbeatEvent().payloadType]:
        #     return
        # elif message.payloadType == ProtoOAApplicationAuthRes().payloadType:
        #     print("API Application authorized\n")
        #     print(
        #         "Please use setAccount command to set the authorized account before sending any other command, try help for more detail\n")
        #     print("To get account IDs use ProtoOAGetAccountListByAccessTokenReq command")
        #     if currentAccountId is not None:
        #         sendProtoOAAccountAuthReq()
        #         return
        # elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
        #     protoOAAccountAuthRes = Protobuf.extract(message)
        #     print(f"Account {protoOAAccountAuthRes.ctidTraderAccountId} has been authorized\n")
        #     print("This acccount will be used for all future requests\n")
        #     print("You can change the account by using setAccount command")
        # else:
        #     print("Message received: \n", Protobuf.extract(message))
        reactor.callLater(3, callable=executeUserCommand)


    def onError(failure):  # Call back for errors
        print("Message Error: ", failure)
        reactor.callLater(3, callable=executeUserCommand)


    def showHelp():
        print("Commands (Parameters with an * are required), ignore the description inside ()")
        print("setAccount(For all subsequent requests this account will be used) *accountId")
        reactor.callLater(3, callable=executeUserCommand)


    def setAccount(accountId):
        global currentAccountId
        if currentAccountId is not None:
            sendProtoOAAccountLogoutReq()
        currentAccountId = int(accountId)
        sendProtoOAAccountAuthReq()


    def sendProtoOAAccountLogoutReq(clientMsgId=None):
        request = ProtoOAAccountLogoutReq()
        request.ctidTraderAccountId = currentAccountId
        deferred = client.send(request, clientMsgId=clientMsgId)
        deferred.addErrback(onError)


    def sendProtoOAAccountAuthReq(clientMsgId=None):
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = currentAccountId
        request.accessToken = accessToken
        deferred = client.send(request, clientMsgId=clientMsgId)
        deferred.addErrback(onError)


    commands = {
        "help": showHelp,
        "setAccount": setAccount,
    }


    def executeUserCommand():
        try:
            print("\n")
            userInput = inputimeout("Command (ex help): ", timeout=18)
        except TimeoutOccurred:
            print("Command Input Timeout")
            reactor.callLater(3, callable=executeUserCommand)
            return
        userInputSplit = userInput.split(" ")
        if not userInputSplit:
            print("Command split error: ", userInput)
            reactor.callLater(3, callable=executeUserCommand)
            return
        command = userInputSplit[0]
        try:
            parameters = [parameter if parameter[0] != "*" else parameter[1:] for parameter in userInputSplit[1:]]
        except:
            print("Invalid parameters: ", userInput)
            reactor.callLater(3, callable=executeUserCommand)
        if command in commands:
            commands[command](*parameters)
        else:
            print("Invalid Command: ", userInput)
            reactor.callLater(3, callable=executeUserCommand)


    # Setting optional client callbacks
    client.setConnectedCallback(connected)
    client.setDisconnectedCallback(disconnected)
    client.setMessageReceivedCallback(onMessageReceived)
    # Starting the client service
    client.startService()
    reactor.run()

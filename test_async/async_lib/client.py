import asyncio

from test_async.async_lib.tcpProtocol import TcpProtocol
from ctrader_open_api.protobuf import Protobuf


class Client:
    def __init__(self, host, port, protocol_factory, number_of_messages_to_send_per_second=5):
        print('*Client __init__')
        self.host = host
        self.port = port
        self.protocol: TcpProtocol = None
        self.protocol_factory = protocol_factory
        self.number_of_messages_to_send_per_second = number_of_messages_to_send_per_second
        self._events = dict()
        self._response_deferreds = dict()
        self.is_connected = False
        self._loop = asyncio.get_event_loop()

    async def start(self):
        print('*Client start')
        transport, protocol = await self._loop.create_connection(
            lambda: self.protocol_factory(self),
            self.host, self.port
        )
        self.transport = transport
        self.protocol = protocol

    async def connected(self, protocol):
        print('*Client connected')
        self.is_connected = True
        if hasattr(self, "_connected_callback"):
            await self._connected_callback(self)

    async def disconnected(self, reason):
        print('*Client disconnected')
        print('DISCONNECTED!!! ')
        self.is_connected = False
        self._response_deferreds.clear()
        if hasattr(self, "_disconnected_callback"):
            await self._disconnected_callback(self, reason)

    async def received(self, message):
        print('*Client received')

        if hasattr(self, "_message_received_callback"):
            await self._message_received_callback(self, message)
        if (message.clientMsgId is not None and message.clientMsgId in self._response_deferreds):
            response_deferred: asyncio.Future = self._response_deferreds[message.clientMsgId]

            print(f'response_deferred: {response_deferred}')
            self._response_deferreds.pop(message.clientMsgId)
            print(f'response_deferred result: {response_deferred.result()}')
            response_deferred.set_result(message)

    async def _send_message(self, message, clientMsgId):
        print('*Client _send_message')
        protocol: TcpProtocol = self.protocol_factory(self)
        protocol.send(message, clientMsgId=clientMsgId, is_canceled=lambda: clientMsgId not in self._response_deferreds)
        self._response_deferreds[clientMsgId].set_result("Message sent successfully")

    async def send(self, message, clientMsgId=None, response_timeout_in_seconds=50, **params):
        print('*Client send')
        if type(message) in [str, int]:
            message = Protobuf.get(message, **params)
        response_future = self._loop.create_future()
        if clientMsgId is None:
            clientMsgId = str(id(response_future))
        if clientMsgId is not None:
            self._response_deferreds[clientMsgId] = response_future

        await asyncio.sleep(1)

        # print(f'send protocol: {self.protocol}')
        # await self.protocol.send(message, clientMsgId=clientMsgId,
        #                    is_canceled=lambda: clientMsgId not in self._response_deferreds)

        # await asyncio.sleep(1)

        try:

            print(f'self._response_deferreds: {self._response_deferreds}')
            await self._send_message(message, clientMsgId=clientMsgId)

            print(f'response_future: {response_future}')

            if response_future.done():
                response = response_future.result()  # Get the result if available
            else:
                response = await asyncio.wait_for(response_future, timeout=response_timeout_in_seconds)

        except asyncio.TimeoutError:
            self._on_response_failure(clientMsgId)
            print(f'TimeoutError: {response}')
            raise
        finally:
            self._response_deferreds.pop(clientMsgId, None)

        return response

    def _on_response_failure(self, clientMsgId):
        print('*Client _on_response_failure')
        if clientMsgId in self._response_futures:
            future = self._response_futures.pop(clientMsgId)
            future.set_exception(asyncio.TimeoutError())

    def setConnectedCallback(self, callback):
        print('*Client setConnectedCallback')
        self._connected_callback = callback

    def setDisconnectedCallback(self, callback):
        print('*Client setDisconnectedCallback')
        self._disconnected_callback = callback

    def setMessageReceivedCallback(self, callback):
        print('*Client setMessageReceivedCallback')
        self._message_received_callback = callback

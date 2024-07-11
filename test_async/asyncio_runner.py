#!/usr/bin/env python

import calendar
import asyncio
import datetime
from collections import deque
from inputimeout import inputimeout, TimeoutOccurred
from ctrader_open_api.endpoints import EndPoints
from ctrader_open_api.protobuf import Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *


class TcpProtocol(asyncio.Protocol):
    MAX_LENGTH = 15000000

    def __init__(self, client):
        self.client = client
        self.transport = None
        self._send_queue = deque([])
        self._send_task = None
        self._last_send_message_time = None

    def connection_made(self, transport):
        self.transport = transport
        self._send_task = asyncio.create_task(self._send_strings())
        asyncio.create_task(self.client.connected(self))

    def connection_lost(self, exc):
        self._send_task.cancel()
        asyncio.create_task(self.client.disconnected(exc))

    def heartbeat(self):
        self.send(ProtoHeartbeatEvent(), True)

    def send(self, message, instant=False, client_msg_id=None, is_canceled=None):
        data = b''

        if isinstance(message, ProtoMessage):
            data = message.SerializeToString()

        if isinstance(message, bytes):
            data = message

        if isinstance(message, ProtoMessage.__base__):
            msg = ProtoMessage(payload=message.SerializeToString(),
                               clientMsgId=client_msg_id,
                               payloadType=message.payloadType)
            data = msg.SerializeToString()

        print(f'protocol _send data: {data}')

        if instant:
            self.transport.write(data)
            self._last_send_message_time = datetime.datetime.now()
        else:
            self._send_queue.append((is_canceled, data))

    async def _send_strings(self):
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
        msg = ProtoMessage()
        msg.ParseFromString(data)

        if msg.payloadType == ProtoHeartbeatEvent().payloadType:
            self.heartbeat()
        asyncio.create_task(self.client.received(msg))


class Client:
    def __init__(self, host, port, protocol_factory, number_of_messages_to_send_per_second=5):
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
        transport, protocol = await self._loop.create_connection(
            lambda: self.protocol_factory(self),
            self.host, self.port
        )
        self.transport = transport
        self.protocol = protocol
        print(f'self.protocol = {protocol}')
        print('start finished')

    async def connected(self, protocol):
        self.is_connected = True
        print(f'connected')
        if hasattr(self, "_connected_callback"):
            await self._connected_callback(self)

    async def disconnected(self, reason):
        self.is_connected = False
        self._response_deferreds.clear()
        if hasattr(self, "_disconnected_callback"):
            await self._disconnected_callback(self, reason)

    async def received(self, message):
        if hasattr(self, "_message_received_callback"):
            await self._message_received_callback(self, message)
        if (message.clientMsgId is not None and message.clientMsgId in self._response_deferreds):
            response_deferred = self._response_deferreds[message.clientMsgId]
            self._response_deferreds.pop(message.clientMsgId)
            response_deferred.set_result(message)

    async def send(self, message, client_msg_id=None, response_timeout_in_seconds=20, **params):
        print(f'try to send request: {message}')
        if type(message) in [str, int]:
            message = Protobuf.get(message, **params)
        response_future = self._loop.create_future()
        if client_msg_id is None:
            client_msg_id = str(id(response_future))
        if client_msg_id is not None:
            self._response_deferreds[client_msg_id] = response_future

        await asyncio.sleep(1)

        print(f'send protocol: {self.protocol}')
        self.protocol.send(message, client_msg_id=client_msg_id,
                           is_canceled=lambda: client_msg_id not in self._response_deferreds)

        try:
            print(f'response_future: {response_future.result()}')
            return await asyncio.wait_for(response_future, timeout=response_timeout_in_seconds)
        except asyncio.TimeoutError:
            print('timeout error??')
            if client_msg_id in self._response_deferreds:
                self._response_deferreds.pop(client_msg_id)
            raise

    def set_connected_callback(self, callback):
        self._connected_callback = callback

    def set_disconnected_callback(self, callback):
        self._disconnected_callback = callback

    def set_message_received_callback(self, callback):
        self._message_received_callback = callback


async def main():
    currentAccountId = 26213142
    host_type = 'demo'

    appClientId = '5914_LRMBD0LJWuue78FqcOxTADdXpOqjDrrphnZiyUjCJC3yEqGlaM'
    appClientSecret = 'm5IDK3v7iJnJcDHvo4RJjnyRv7CHEun5VjR57K4zQ8YLDcjTCJ'
    accessToken = '5buBFoMeswX8jCd-4URRkWCjBA4Jg_2sGtEZL25kMAY'

    client = Client(EndPoints.PROTOBUF_LIVE_HOST if host_type.lower() == "live" else EndPoints.PROTOBUF_DEMO_HOST,
                    EndPoints.PROTOBUF_PORT, TcpProtocol)

    async def connected(client: Client):
        print(f'-- connected client: {client}')

        print("\nConnected")
        request = ProtoOAApplicationAuthReq()
        request.clientId = appClientId
        request.clientSecret = appClientSecret
        try:
            await client.send(request)
        except Exception as e:
            await onError(e)

    async def disconnected(client, reason):
        print("\nDisconnected: ", reason)

    async def on_message_received(client, message):
        if message.payloadType in [ProtoOASubscribeSpotsRes().payloadType, ProtoOAAccountLogoutRes().payloadType,
                                   ProtoHeartbeatEvent().payloadType]:
            return
        elif message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            print("API Application authorized\n")
            print(
                "Please use setAccount command to set the authorized account before sending any other command, try help for more detail\n")
            print("To get account IDs use ProtoOAGetAccountListByAccessTokenReq command")
            if current_account_id is not None:
                await send_proto_oa_account_auth_req()
                return
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            proto_oa_account_auth_res = Protobuf.extract(message)
            print(f"Account {proto_oa_account_auth_res.ctidTraderAccountId} has been authorized\n")
            print("This account will be used for all future requests\n")
            print("You can change the account by using setAccount command")
        else:
            print("Message received: \n", Protobuf.extract(message))
        await asyncio.sleep(3)
        await execute_user_command()

    async def onError(failure):
        print("Message Error: ", failure)
        await asyncio.sleep(3)
        await execute_user_command()

    async def showHelp():
        print("Commands (Parameters with an * are required), ignore the description inside ()")
        print("setAccount(For all subsequent requests this account will be used) *accountId")
        print("ProtoOAVersionReq clientMsgId")
        print("ProtoOAGetAccountListByAccessTokenReq clientMsgId")
        print("ProtoOAAssetListReq clientMsgId")
        print("ProtoOAAssetClassListReq clientMsgId")
        print("ProtoOASymbolCategoryListReq clientMsgId")
        print("ProtoOASymbolsListReq includeArchivedSymbols(True/False) clientMsgId")
        print("ProtoOATraderReq clientMsgId")
        print("ProtoOASubscribeSpotsReq *symbolId *timeInSeconds(Unsubscribes after this time) subscribeToSpotTimestamp(True/False) clientMsgId")
        print("ProtoOAReconcileReq clientMsgId")
        print("ProtoOAGetTrendbarsReq *weeks *period *symbolId clientMsgId")
        print("ProtoOAGetTickDataReq *days *type *symbolId clientMsgId")
        print("NewMarketOrder *symbolId *tradeSide *volume clientMsgId")
        print("NewLimitOrder *symbolId *tradeSide *volume *price clientMsgId")
        print("NewStopOrder *symbolId *tradeSide *volume *price clientMsgId")
        print("ClosePosition *positionId *volume clientMsgId")
        print("CancelOrder *orderId clientMsgId")
        print("DealOffsetList *dealId clientMsgId")
        print("GetPositionUnrealizedPnL clientMsgId")
        print("OrderDetails clientMsgId")
        print("OrderListByPositionId *positionId fromTimestamp toTimestamp clientMsgId")
        await asyncio.sleep(3)
        await execute_user_command()

    async def setAccount(account_id):
        nonlocal currentAccountId
        if currentAccountId is not None:
            await sendProtoOAAccountLogoutReq()
        currentAccountId = int(account_id)
        await sendProtoOAAccountAuthReq()

    async def sendProtoOAAccountLogoutReq(client_msg_id=None):
        request = ProtoOAAccountLogoutReq()
        request.ctidTraderAccountId = current_account_id
        try:
            await client.send(request, client_msg_id=client_msg_id)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAccountAuthReq(client_msg_id=None):
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = current_account_id
        request.accessToken = accessToken
        try:
            await client.send(request, client_msg_id=client_msg_id)
        except Exception as e:
            await onError(e)

    async def sendProtoOAVersionReq(client_msg_id=None):
        request = ProtoOAVersionReq()
        try:
            await client.send(request, client_msg_id=client_msg_id)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetAccountListByAccessTokenReq(client_msg_id=None):
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = accessToken
        try:
            await client.send(request, client_msg_id=client_msg_id)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAssetListReq(clientMsgId = None):
        request = ProtoOAAssetListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAssetClassListReq(clientMsgId = None):
        request = ProtoOAAssetClassListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASymbolCategoryListReq(clientMsgId = None):
        request = ProtoOASymbolCategoryListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASymbolsListReq(includeArchivedSymbols = False, clientMsgId = None):
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = currentAccountId
        request.includeArchivedSymbols = includeArchivedSymbols if type(includeArchivedSymbols) is bool else bool(includeArchivedSymbols)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)


    async def sendProtoOATraderReq(clientMsgId = None):
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAUnsubscribeSpotsReq(symbolId, clientMsgId = None):
        request = ProtoOAUnsubscribeSpotsReq()
        request.ctidTraderAccountId = currentAccountId
        request.symbolId.append(int(symbolId))
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASubscribeSpotsReq(symbolId, timeInSeconds, subscribeToSpotTimestamp	= False, clientMsgId = None):
        request = ProtoOASubscribeSpotsReq()
        request.ctidTraderAccountId = currentAccountId
        request.symbolId.append(int(symbolId))
        request.subscribeToSpotTimestamp = subscribeToSpotTimestamp if type(subscribeToSpotTimestamp) is bool else bool(subscribeToSpotTimestamp)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)
        await asyncio.sleep(int(timeInSeconds))
        await sendProtoOAUnsubscribeSpotsReq(symbolId)

    async def sendProtoOAReconcileReq(clientMsgId = None):
        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetTrendbarsReq(weeks, period, symbolId, clientMsgId = None):
        request = ProtoOAGetTrendbarsReq()
        request.ctidTraderAccountId = currentAccountId
        request.period = ProtoOATrendbarPeriod.Value(period)
        request.fromTimestamp = int(calendar.timegm((datetime.datetime.utcnow() - datetime.timedelta(weeks=int(weeks))).utctimetuple())) * 1000
        request.toTimestamp = int(calendar.timegm(datetime.datetime.utcnow().utctimetuple())) * 1000
        request.symbolId = int(symbolId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetTickDataReq(days, quoteType, symbolId, clientMsgId = None):
        request = ProtoOAGetTickDataReq()
        request.ctidTraderAccountId = currentAccountId
        request.type = ProtoOAQuoteType.Value(quoteType.upper())
        request.fromTimestamp = int(calendar.timegm((datetime.datetime.utcnow() - datetime.timedelta(days=int(days))).utctimetuple())) * 1000
        request.toTimestamp = int(calendar.timegm(datetime.datetime.utcnow().utctimetuple())) * 1000
        request.symbolId = int(symbolId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOANewOrderReq(symbolId, orderType, tradeSide, volume, price = None, clientMsgId = None):
        request = ProtoOANewOrderReq()
        request.ctidTraderAccountId = currentAccountId
        request.symbolId = int(symbolId)
        request.orderType = ProtoOAOrderType.Value(orderType.upper())
        request.tradeSide = ProtoOATradeSide.Value(tradeSide.upper())
        request.volume = int(volume) * 100
        if request.orderType == ProtoOAOrderType.LIMIT:
            request.limitPrice = float(price)
        elif request.orderType == ProtoOAOrderType.STOP:
            request.stopPrice = float(price)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendNewMarketOrder(symbolId, tradeSide, volume, clientMsgId = None):
        sendProtoOANewOrderReq(symbolId, "MARKET", tradeSide, volume, clientMsgId = clientMsgId)

    async def sendNewLimitOrder(symbolId, tradeSide, volume, price, clientMsgId = None):
        sendProtoOANewOrderReq(symbolId, "LIMIT", tradeSide, volume, price, clientMsgId)

    async def sendNewStopOrder(symbolId, tradeSide, volume, price, clientMsgId = None):
        sendProtoOANewOrderReq(symbolId, "STOP", tradeSide, volume, price, clientMsgId)

    async def sendProtoOAClosePositionReq(positionId, volume, clientMsgId = None):
        request = ProtoOAClosePositionReq()
        request.ctidTraderAccountId = currentAccountId
        request.positionId = int(positionId)
        request.volume = int(volume) * 100
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOACancelOrderReq(orderId, clientMsgId = None):
        request = ProtoOACancelOrderReq()
        request.ctidTraderAccountId = currentAccountId
        request.orderId = int(orderId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOADealOffsetListReq(dealId, clientMsgId=None):
        request = ProtoOADealOffsetListReq()
        request.ctidTraderAccountId = currentAccountId
        request.dealId = int(dealId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetPositionUnrealizedPnLReq(clientMsgId=None):
        request = ProtoOAGetPositionUnrealizedPnLReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAOrderDetailsReq(orderId, clientMsgId=None):
        request = ProtoOAOrderDetailsReq()
        request.ctidTraderAccountId = currentAccountId
        request.orderId = int(orderId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAOrderListByPositionIdReq(positionId, fromTimestamp=None, toTimestamp=None, clientMsgId=None):
        request = ProtoOAOrderListByPositionIdReq()
        request.ctidTraderAccountId = currentAccountId
        request.positionId = int(positionId)
        try:
            await client.send(request, client_msg_id=clientMsgId)
        except Exception as e:
            await onError(e)

    commands = {
        "help": showHelp,
        "setAccount": setAccount,
        "ProtoOAVersionReq": sendProtoOAVersionReq,
        "ProtoOAGetAccountListByAccessTokenReq": sendProtoOAGetAccountListByAccessTokenReq,
        "ProtoOAAssetListReq": sendProtoOAAssetListReq,
        "ProtoOAAssetClassListReq": sendProtoOAAssetClassListReq,
        "ProtoOASymbolCategoryListReq": sendProtoOASymbolCategoryListReq,
        "ProtoOASymbolsListReq": sendProtoOASymbolsListReq,
        "ProtoOATraderReq": sendProtoOATraderReq,
        "ProtoOASubscribeSpotsReq": sendProtoOASubscribeSpotsReq,
        "ProtoOAReconcileReq": sendProtoOAReconcileReq,
        "ProtoOAGetTrendbarsReq": sendProtoOAGetTrendbarsReq,
        "ProtoOAGetTickDataReq": sendProtoOAGetTickDataReq,
        "NewMarketOrder": sendNewMarketOrder,
        "NewLimitOrder": sendNewLimitOrder,
        "NewStopOrder": sendNewStopOrder,
        "ClosePosition": sendProtoOAClosePositionReq,
        "CancelOrder": sendProtoOACancelOrderReq,
        "DealOffsetList": sendProtoOADealOffsetListReq,
        "GetPositionUnrealizedPnL": sendProtoOAGetPositionUnrealizedPnLReq,
        "OrderDetails": sendProtoOAOrderDetailsReq,
        "OrderListByPositionId": sendProtoOAOrderListByPositionIdReq,
    }

    async def execute_user_command():
        try:
            print("\n")
            user_input = await asyncio.wait_for(asyncio.to_thread(inputimeout, "Command (ex help): ", 180), 180)
        except TimeoutOccurred:
            print("Command Input Timeout")
            await asyncio.sleep(3)
            await execute_user_command()
            return
        except asyncio.TimeoutError:
            print("Command Input Timeout")
            await asyncio.sleep(3)
            await execute_user_command()
            return
        user_input_split = user_input.split(" ")
        if not user_input_split:
            print("Command split error: ", user_input)
            await asyncio.sleep(3)
            await execute_user_command()
            return
        command = user_input_split[0]
        try:
            parameters = [parameter if parameter[0] != "*" else parameter[1:] for parameter in user_input_split[1:]]
        except Exception:
            print("Invalid parameters: ", user_input)
            await asyncio.sleep(3)
            await execute_user_command()
            return
        if command in commands:
            await commands[command](*parameters)
        else:
            print("Invalid Command: ", user_input)
            await asyncio.sleep(3)
            await execute_user_command()

    client.set_connected_callback(connected)
    client.set_disconnected_callback(disconnected)
    client.set_message_received_callback(on_message_received)

    await client.start()
    await asyncio.sleep(3)
    await execute_user_command()

if __name__ == "__main__":
    asyncio.run(main())

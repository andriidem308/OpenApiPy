import calendar
import datetime
from inputimeout import inputimeout, TimeoutOccurred
import asyncio

from test_async.async_lib.tcpProtocol import TcpProtocol
from test_async.async_lib.client import Client
from test_async.async_lib.endpoints import EndPoints
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *


async def main():
    currentAccountId = 26213142
    host_type = 'demo'

    appClientId = '5914_LRMBD0LJWuue78FqcOxTADdXpOqjDrrphnZiyUjCJC3yEqGlaM'
    appClientSecret = 'm5IDK3v7iJnJcDHvo4RJjnyRv7CHEun5VjR57K4zQ8YLDcjTCJ'
    accessToken = '5buBFoMeswX8jCd-4URRkWCjBA4Jg_2sGtEZL25kMAY'

    client = Client(EndPoints.PROTOBUF_LIVE_HOST if host_type.lower() == "live" else EndPoints.PROTOBUF_DEMO_HOST,
                    EndPoints.PROTOBUF_PORT, TcpProtocol)

    async def connected(client: Client):
        print("\n--- Connected! ---")
        request = ProtoOAApplicationAuthReq()
        request.clientId = appClientId
        request.clientSecret = appClientSecret
        try:
            await client.send(request)
        except Exception as e:
            await onError(e)

    async def disconnected(client, reason):
        print("\nDisconnected: ", reason)

    async def onMessageReceived(client, message):
        print('onMessageReceived start')

        if message.payloadType in [ProtoOASubscribeSpotsRes().payloadType, ProtoOAAccountLogoutRes().payloadType,
                                   ProtoHeartbeatEvent().payloadType]:
            return
        elif message.payloadType == ProtoOAApplicationAuthRes().payloadType:
            print("API Application authorized\n")
            print(
                "Please use setAccount command to set the authorized account before sending any other command, try help for more detail\n")
            print("To get account IDs use ProtoOAGetAccountListByAccessTokenReq command")
            if currentAccountId is not None:
                await sendProtoOAAccountAuthReq()
                return
        elif message.payloadType == ProtoOAAccountAuthRes().payloadType:
            proto_oa_account_auth_res = Protobuf.extract(message)
            print(f"Account {proto_oa_account_auth_res.ctidTraderAccountId} has been authorized\n")
            print("This account will be used for all future requests\n")
            print("You can change the account by using setAccount command")
        else:
            print("Message received: \n", Protobuf.extract(message))
        await asyncio.sleep(3)
        await executeUserCommand()

    async def onError(failure):
        raise failure
        print("Message Error: ", failure)
        await asyncio.sleep(3)
        await executeUserCommand()

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
        await executeUserCommand()

    async def setAccount(account_id):
        nonlocal currentAccountId
        if currentAccountId is not None:
            await sendProtoOAAccountLogoutReq()
        currentAccountId = int(account_id)
        await sendProtoOAAccountAuthReq()

    async def sendProtoOAAccountLogoutReq(clientMsgId=None):
        request = ProtoOAAccountLogoutReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAccountAuthReq(clientMsgId=None):
        request = ProtoOAAccountAuthReq()
        request.ctidTraderAccountId = currentAccountId
        request.accessToken = accessToken
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAVersionReq(clientMsgId=None):
        request = ProtoOAVersionReq()
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetAccountListByAccessTokenReq(clientMsgId=None):
        request = ProtoOAGetAccountListByAccessTokenReq()
        request.accessToken = accessToken
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAssetListReq(clientMsgId = None):
        request = ProtoOAAssetListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAAssetClassListReq(clientMsgId = None):
        request = ProtoOAAssetClassListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASymbolCategoryListReq(clientMsgId = None):
        request = ProtoOASymbolCategoryListReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASymbolsListReq(includeArchivedSymbols = False, clientMsgId = None):
        request = ProtoOASymbolsListReq()
        request.ctidTraderAccountId = currentAccountId
        request.includeArchivedSymbols = includeArchivedSymbols if type(includeArchivedSymbols) is bool else bool(includeArchivedSymbols)
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)


    async def sendProtoOATraderReq(clientMsgId = None):
        request = ProtoOATraderReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAUnsubscribeSpotsReq(symbolId, clientMsgId = None):
        request = ProtoOAUnsubscribeSpotsReq()
        request.ctidTraderAccountId = currentAccountId
        request.symbolId.append(int(symbolId))
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOASubscribeSpotsReq(symbolId, timeInSeconds, subscribeToSpotTimestamp	= False, clientMsgId = None):
        request = ProtoOASubscribeSpotsReq()
        request.ctidTraderAccountId = currentAccountId
        request.symbolId.append(int(symbolId))
        request.subscribeToSpotTimestamp = subscribeToSpotTimestamp if type(subscribeToSpotTimestamp) is bool else bool(subscribeToSpotTimestamp)
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)
        await asyncio.sleep(int(timeInSeconds))
        await sendProtoOAUnsubscribeSpotsReq(symbolId)

    async def sendProtoOAReconcileReq(clientMsgId = None):
        request = ProtoOAReconcileReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
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
            await client.send(request, clientMsgId=clientMsgId)
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
            await client.send(request, clientMsgId=clientMsgId)
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
            await client.send(request, clientMsgId=clientMsgId)
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
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOACancelOrderReq(orderId, clientMsgId = None):
        request = ProtoOACancelOrderReq()
        request.ctidTraderAccountId = currentAccountId
        request.orderId = int(orderId)
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOADealOffsetListReq(dealId, clientMsgId=None):
        request = ProtoOADealOffsetListReq()
        request.ctidTraderAccountId = currentAccountId
        request.dealId = int(dealId)
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAGetPositionUnrealizedPnLReq(clientMsgId=None):
        request = ProtoOAGetPositionUnrealizedPnLReq()
        request.ctidTraderAccountId = currentAccountId
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAOrderDetailsReq(orderId, clientMsgId=None):
        request = ProtoOAOrderDetailsReq()
        request.ctidTraderAccountId = currentAccountId
        request.orderId = int(orderId)
        try:
            await client.send(request, clientMsgId=clientMsgId)
        except Exception as e:
            await onError(e)

    async def sendProtoOAOrderListByPositionIdReq(positionId, fromTimestamp=None, toTimestamp=None, clientMsgId=None):
        request = ProtoOAOrderListByPositionIdReq()
        request.ctidTraderAccountId = currentAccountId
        request.positionId = int(positionId)
        try:
            await client.send(request, clientMsgId=clientMsgId)
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

    async def executeUserCommand():
        try:
            print("\n")
            # TODO: set timeout 18
            # user_input = await asyncio.to_thread(inputimeout, "Command (ex help): ", 5)
            user_input = await asyncio.wait_for(asyncio.to_thread(inputimeout, "Command (ex help): ", 180), 180)
        except TimeoutOccurred:
            print("Command Input Timeout: TimeoutOccurred")
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        except asyncio.TimeoutError:
            print("Command Input Timeout: asyncio.TimeoutError")
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        user_input_split = user_input.split(" ")
        if not user_input_split:
            print("Command split error: ", user_input)
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        command = user_input_split[0]
        try:
            parameters = [parameter if parameter[0] != "*" else parameter[1:] for parameter in user_input_split[1:]]
        except Exception:
            print("Invalid parameters: ", user_input)
            await asyncio.sleep(3)
            await executeUserCommand()
            return
        if command in commands:
            await commands[command](*parameters)
        else:
            print("Invalid Command: ", user_input)
            await asyncio.sleep(3)
            await executeUserCommand()

    client.setConnectedCallback(connected)
    client.setDisconnectedCallback(disconnected)
    client.setMessageReceivedCallback(onMessageReceived)

    await client.start()
    await asyncio.sleep(3)
    await executeUserCommand()

if __name__ == "__main__":
    asyncio.run(main())

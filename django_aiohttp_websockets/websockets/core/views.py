from aiohttp import web, WSMsgType


class WebSocketView(web.View):

    def __init__(self, *args, **kwargs):
        super(WebSocketView, self).__init__(*args, **kwargs)
        self.app = self.request.app

    async def get(self):

        ws = web.WebSocketResponse()
        await ws.prepare(self.request)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
                else:
                    ws.send_str(msg.data + '/answer')
            elif msg.type == WSMsgType.ERROR:
                print('ws connection closed with exception %s' %
                      ws.exception())

        print('websocket connection closed')
        return ws

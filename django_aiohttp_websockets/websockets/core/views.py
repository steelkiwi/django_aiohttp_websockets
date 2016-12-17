import json

from aiohttp import web, WSMsgType, WSCloseCode


class WebSocketView(web.View):

    def __init__(self, *args, **kwargs):
        super(WebSocketView, self).__init__(*args, **kwargs)
        self.app = self.request.app
        self.logger = self.app.logger

    async def get(self):
        ws = web.WebSocketResponse()
        await ws.prepare(self.request)

        ws_id = id(ws)
        self.logger.debug('[%s] New websocket connection', ws_id)
        self.app.handle_ws_connect(ws, self)

        async for msg_raw in ws:
            if msg_raw.tp == WSMsgType.TEXT:
                try:
                    msg = json.loads(msg_raw.data)
                    self.logger.debug('[%s] Publish message %s to redis', ws_id, msg)
                    await self.app.publish_message_to_worker(ws, msg)
                except Exception as e:
                    self.logger.error('[%s] Invalid message format. Exception: %s', ws_id, e)
                    await ws.close(code=WSCloseCode.UNSUPPORTED_DATA, message=str(e))
                    break

            elif msg_raw.tp == WSMsgType.ERROR:
                self.logger.error('[%s] ERROR WS connection closed with exception: %s', ws_id, ws.exception())

        self.logger.debug('[%s] Websocket connection closed', ws_id)
        self.app.handle_ws_disconnect(ws)
        return ws

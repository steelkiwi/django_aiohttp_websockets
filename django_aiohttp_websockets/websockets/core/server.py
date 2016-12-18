import asyncio
import json
import logging
import random

import aioredis
from aiohttp import web, WSCloseCode

from django_aiohttp_websockets.websockets.core import views, settings, utils


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(process)d - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')  # noqa
console.setFormatter(formatter)
logger.addHandler(console)


class WSApplication(web.Application):
    WS_MESSAGE_REQUIRED_KEYS = ['uuid', ]

    def __init__(self, **kwargs):
        super(WSApplication, self).__init__(**kwargs)
        self.tasks = []
        self.websockets = {}
        self.logger = logger

        self.on_shutdown.append(self._on_shutdown_handler)
        self.loop.run_until_complete(self._setup())

    async def _setup(self):
        self.router.add_get('/ws', views.WebSocketView)
        self.redis_subscriber = await aioredis.create_redis((settings.REDIS_HOST, settings.REDIS_PORT), loop=self.loop)
        self.redis_publisher = await aioredis.create_redis((settings.REDIS_HOST, settings.REDIS_PORT), loop=self.loop)
        self.tasks.append(self.loop.create_task(self.subscribe_to_channel(settings.WORKER_RESPONSE_TOPIC)))

    async def _on_shutdown_handler(self, app):
        for task in self.tasks:
            task.cancel()
            await task

        for ws in self.websockets:
            await ws.close(code=WSCloseCode.GOING_AWAY, message='Server shutdown')

        for redis_conn in [self.redis_subscriber, self.redis_publisher]:
            if redis_conn and not redis_conn.closed:
                redis_conn.close()
                await redis_conn.wait_closed()

    async def subscribe_to_channel(self, topic):
        self.logger.info('Subscribe to channel: %s', topic)
        try:
            channel, *_ = await self.redis_subscriber.subscribe(topic)

            while await channel.wait_message():
                try:
                    raw_msg = await channel.get()
                    msg = json.loads(raw_msg.decode('utf-8'))
                    await self.process_worker_response(msg)

                except (json.JSONDecodeError, ValueError, Exception) as e:
                    self.logger.error('Exception while processing redis msg: %s', e)

        except asyncio.CancelledError:
            self.logger.error('CancelledError exception received. Unsubscribe from channel: %s', topic)
            await self.redis_subscriber.unsubscribe(topic)

    def handle_ws_connect(self, ws, view):
        self.websockets[ws] = {
            'view': view,
            'messages_ids': [],
            'session_data': {
                'user_pk': None
            }
        }
        self.logger.debug('[%s] Websocket was added to websocket list', id(ws))

    def handle_ws_disconnect(self, ws):
        self.websockets.pop(ws, None)
        self.logger.debug('[%s] Websocket was removed from websockets list', id(ws))

    async def publish_message_to_worker(self, ws, msg):
        if not all(msg.get(key) for key in self.WS_MESSAGE_REQUIRED_KEYS):
            raise Exception('Missing required keys')

        msg_id = msg['uuid']
        publish_topic = random.choice(settings.WORKER_PROCESS_TOPICS)

        msg['session_data'] = self.websockets[ws]['session_data']
        self.websockets[ws]['messages_ids'].append(msg_id)
        self.logger.debug('[%s] Publish message with id \'%s\' to topic \'%s\'', id(ws), msg_id, publish_topic)
        await self.redis_publisher.publish_json(publish_topic, msg)

    def _find_ws_by_message_uuid(self, msg_uuid):
        for ws, ws_data in self.websockets.items():
            if msg_uuid in ws_data.get('messages_ids', []):
                return ws

    def _find_ws_by_send_to(self, send_to):
        websockets = []
        for ws, ws_data in self.websockets.items():
            if ws_data.get('session_data', {}).get('user_pk') in send_to:
                websockets.append(ws)
        return websockets

    def _update_session(self, ws, response_msg):
        if response_msg.get('session_data'):
            self.websockets[ws]['session_data'] = response_msg['session_data']

    async def process_worker_response(self, response_msg):
        response = response_msg['response']
        msg_uuid = response['uuid']
        send_to = response_msg.get('send_to')
        self.logger.debug('Processing response for msg with id \'%s\'', msg_uuid)

        ws = self._find_ws_by_message_uuid(msg_uuid)
        if response_msg['type'] == utils.ERROR_RESPONSE_TYPE:
            if ws:
                ws.send_str(json.dumps(response))

        elif response_msg['type'] == utils.SUCCESS_RESPONSE_TYPE:
            self._update_session(ws, response_msg)
            if not send_to:
                if ws:
                    ws.send_str(json.dumps(response))
            else:
                websockets = self._find_ws_by_send_to(send_to)
                for ws in websockets:
                    ws.send_str(json.dumps(response))

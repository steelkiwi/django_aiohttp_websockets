import asyncio
import json
import logging

import aioredis
from aiohttp import web, WSCloseCode

from django_aiohttp_websockets.websockets.core import views, settings


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(process)d - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
console.setFormatter(formatter)
logger.addHandler(console)


class WSApplication(web.Application):

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
        self.tasks.append(self.loop.create_task(self.subscribe_to_channel(settings.WORKER_RESPONSE_TOPIC)))

    async def _on_shutdown_handler(self, app):
        for task in self.tasks:
            task.cancel()
            await task

        for ws in self.websockets:
            await ws.close(code=WSCloseCode.GOING_AWAY, message='Server shutdown')

        if self.redis_subscriber and not self.redis_subscriber.closed:
            self.redis_subscriber.close()
            await self.redis_subscriber.wait_closed()

    async def subscribe_to_channel(self, topic):
        self.logger.info('Subscribe to channel: %s', topic)
        try:
            channel, *_ = await self.redis_subscriber.subscribe(topic)

            while await channel.wait_message():
                try:
                    raw_msg = await channel.get()
                    msg = json.loads(raw_msg.decode('utf-8'))
                    # process message here

                except (json.JSONDecodeError, ValueError, Exception) as e:
                    self.logger.error('Exception while processing redis msg: %s', e)

        except asyncio.CancelledError:
            self.logger.error('CancelledError exception received. Unsubscribe from channel: %s', topic)
            await self.redis_subscriber.unsubscribe(topic)

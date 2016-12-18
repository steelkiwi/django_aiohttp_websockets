import asyncio
import json
import signal

import aioredis

from django_aiohttp_websockets.websockets.core import settings
from django_aiohttp_websockets.websockets.core.worker_message_handlers import MessageProcessHandler


class AioredisWorker(object):
    def __init__(self, host, port, subscribe_topic, logger, loop=None, **kwargs):
        self.logger = logger
        self.loop = loop or asyncio.get_event_loop()
        self.host = host
        self.port = port
        self.subscribe_topic = subscribe_topic
        self.redis_subscriber = None
        self.redis_publisher = None
        self.tasks = []
        self.message_process_handler = MessageProcessHandler(logger=self.logger)

        self.loop.add_signal_handler(signal.SIGTERM, self.shutdown)
        self.loop.add_signal_handler(signal.SIGINT, self.shutdown)

    async def _shutdown(self):
        for task in self.tasks:
            task.cancel()
            await task

        for redis_conn in [self.redis_subscriber, self.redis_publisher]:
            if redis_conn and not redis_conn.closed:
                redis_conn.close()
                await redis_conn.wait_closed()

    def shutdown(self):
        self.logger.info('Shutdown initiated. Unsubscribing from all channels')
        self.loop.run_until_complete(self._shutdown())
        self.loop.stop()
        self.loop.close()

    async def subscribe_to_channel(self, ch):
        try:
            channel, *_ = await self.redis_subscriber.subscribe(ch)
            while (await channel.wait_message()):
                try:
                    raw_msg = await channel.get()
                    msg = json.loads(raw_msg.decode('utf-8'))
                    self.logger.debug('Processing message %s', msg)
                    response = self.message_process_handler.process_message(msg)
                    await self.redis_publisher.publish_json(settings.WORKER_RESPONSE_TOPIC, response)
                except Exception as e:
                    self.logger.error('Exception while processing redis msg: %s', e)

        except asyncio.CancelledError:
            self.logger.error('CancelledError exception received. Unsubscribe from channel %s', ch)
            await self.redis_subscriber.unsubscribe(ch)

    async def _run(self):
        self.logger.info('Redis connection at %s:%s. Subscribed to: %s.', self.host, self.port, self.subscribe_topic)
        self.redis_subscriber = await aioredis.create_redis((self.host, self.port), loop=self.loop)
        self.redis_publisher = await aioredis.create_redis((self.host, self.port), loop=self.loop)
        self.tasks.append(self.loop.create_task(self.subscribe_to_channel(self.subscribe_topic)))

    def run(self):
        self.loop.run_until_complete(self._run())
        self.loop.run_forever()

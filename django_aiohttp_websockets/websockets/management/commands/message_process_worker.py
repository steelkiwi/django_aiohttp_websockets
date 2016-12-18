import logging

from django.core.management import BaseCommand

from django_aiohttp_websockets.websockets.core import settings
from django_aiohttp_websockets.websockets.core.worker import AioredisWorker


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(process)d - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')  # noqa
console.setFormatter(formatter)
logger.addHandler(console)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--host', type=str, default=settings.REDIS_HOST)
        parser.add_argument('--port', type=int, default=settings.REDIS_PORT)
        parser.add_argument('--subscribe_topic', type=str, required=True)

    def handle(self, *args, **options):
        options['logger'] = logger
        AioredisWorker(**options).run()

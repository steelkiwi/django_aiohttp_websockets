from aiohttp import web
from django_aiohttp_websockets.websockets.core import views


app = web.Application()
app.router.add_get('/ws', views.WebSocketView)

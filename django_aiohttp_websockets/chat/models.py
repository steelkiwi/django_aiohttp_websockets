import uuid

from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _


class ChatRoom(models.Model):
    id = models.UUIDField(verbose_name=_('Room ID'), primary_key=True, default=uuid.uuid4, editable=False)
    date_created = models.DateTimeField(verbose_name=_('Created'), auto_now_add=True)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_('User'))

    def __str__(self):
        return 'Room {}'.format(self.id)


class ChatMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'))
    room = models.ForeignKey('chat.ChatRoom', verbose_name=_('Chat room ID'), related_name='messages')
    date_created = models.DateTimeField(verbose_name=_('Created'), auto_now_add=True)
    text = models.TextField(verbose_name=_('Message'))

    def __str__(self):
        return 'Message from {}'.format(self.user)

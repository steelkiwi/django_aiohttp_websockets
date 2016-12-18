from rest_framework import serializers

from django_aiohttp_websockets.users.serializers import UserSerializer
from django_aiohttp_websockets.chat.models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    room = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    user = UserSerializer()

    class Meta:
        model = ChatMessage
        fields = ('id', 'user', 'room', 'timestamp', 'text', )

    def get_timestamp(self, instance):
        return instance.date_created.timestamp()

    def get_room(self, instance):
        return instance.room.pk.hex

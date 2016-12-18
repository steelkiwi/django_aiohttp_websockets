from django.contrib.auth import get_user_model

from django_aiohttp_websockets.chat.models import ChatRoom, ChatMessage
from django_aiohttp_websockets.chat.serializers import ChatMessageSerializer
from django_aiohttp_websockets.websockets.core import utils

User = get_user_model()


class MessageProcessHandler(object):
    REQUIRED_KEYS = ['action', 'uuid', ]
    ACTIONS = ['authenticate', 'select_room', 'new_message', ]
    error_messages = {
        'invalid_message_format': 'Some of required keys are absent or empty. Required keys: %s' % REQUIRED_KEYS,
        'invalid_payload': 'Invalid message action. Next actions are allowed: %s' % ACTIONS,
        'invalid_token': 'Invalid authentication token',
        'authentication_required': 'Authentication required before sending any other messages',
        'invalid_room_id': 'Invalid room id',
        'empty_text': 'Message text can\'t be empty',
    }

    def __init__(self, logger):
        self.logger = logger

    def _error_response(self, msg, error_message):
        return {
            'type': utils.ERROR_RESPONSE_TYPE,
            'response': {
                'uuid': msg.get('uuid'),
                'action': msg.get('action'),
                'error_message': str(error_message),
                'status': 'error',
            }
        }

    def _success_response(self, msg, response=None, send_to=None, session_data=None):
        if response is None:
            response = {}

        response.update({
            'uuid': msg.get('uuid'),
            'action': msg.get('action'),
            'status': 'success',
        })

        resp = {
            'type': utils.SUCCESS_RESPONSE_TYPE,
            'send_to': send_to,
            'session_data': session_data,
            'response': response
        }
        return resp

    def process_message(self, msg):
        try:
            self._validate_message(msg)
            response = getattr(self, 'process_%s' % msg['action'])(msg)
        except Exception as e:
            self.logger.error("Error occurred while processing action: %s", str(e))
            return self._error_response(msg, e)

        return response

    def _validate_message(self, msg):
        if not all(msg.get(key) for key in self.REQUIRED_KEYS):
            raise Exception(self.error_messages['invalid_message_format'])

        if msg['action'] not in self.ACTIONS:
            raise Exception(self.error_messages['invalid_payload'])

        if msg['action'] != 'authenticate' and not msg.get('session_data', {}).get('user_pk'):
            raise Exception(self.error_messages['authentication_required'])

    def _get_room(self, msg):
        try:
            return ChatRoom.objects.get(pk=msg.get('room'), users__pk=msg['session_data']['user_pk'])
        except ChatRoom.DoesNotExist:
            raise Exception(self.error_messages['invalid_room_id'])

    def process_authenticate(self, msg):
        try:
            user = User.objects.get(auth_token__key=msg.get('token'))
        except User.DoesNotExist:
            raise Exception(self.error_messages['invalid_token'])

        return self._success_response(msg, session_data={'user_pk': user.pk})

    def process_select_room(self, msg):
        room = self._get_room(msg)
        messages = reversed(room.messages.all().order_by('-date_created')[:20])
        response = {
            'room': room.pk.hex,
            'room_messages': ChatMessageSerializer(messages, many=True).data,
        }
        return self._success_response(msg, response=response)

    def process_new_message(self, msg):
        room = self._get_room(msg)
        send_to = list(room.users.all().values_list('id', flat=True))

        if not msg.get('text', '').strip():
            raise Exception(self.error_messages['empty_text'])

        chat_message = ChatMessage.objects.create(
            user_id=msg['session_data']['user_pk'],
            text=msg['text'],
            room=room,
        )

        response = {
            'room': room.pk.hex,
            'message': ChatMessageSerializer(chat_message).data,
        }
        return self._success_response(msg, response=response, send_to=send_to)

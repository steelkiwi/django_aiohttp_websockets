class MessageProcessHandler(object):
    def __init__(self, logger):
        self.logger = logger

    def process_message(self, msg):
        return {'test': 'test'}

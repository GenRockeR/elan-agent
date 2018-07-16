import datetime, traceback

from elan.neuron import Dendrite


class Event(object):
    EVENT_TOPIC = 'event'

    def __init__(self, event_type, source, level='info', timestamp=None, dendrite=None):
        if timestamp is None:
            timestamp = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # Epoch

        self.type = event_type
        self.source = source
        self.level = level
        self.timestamp = timestamp
        self.data = []
        self.dendrite = dendrite

    def add_data(self, key, value, data_type=None):
        if data_type is None:
            item = dict(key=key, value=value)
        else:
            item = dict(key=key, value=value, type=data_type)
        self.data.append(item)

        return self

    def notify(self):
        data = {
                'type':        self.type,
                'source':      self.source,
                'level':       self.level,
                'timestamp':   datetime.datetime.utcfromtimestamp(self.timestamp).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'data':        self.data,
        }

        if self.dendrite is None:
            return Dendrite.publish_single(self.EVENT_TOPIC, data)
        else:
            return self.dendrite.publish(self.EVENT_TOPIC, data)


class DebugEvent(Event):
    EVENT_TOPIC = 'debug'

    def __init__(self, source, event_type='runtime', level='info', **kwargs):
        super().__init__(event_type, source, level=level, **kwargs)


class ExceptionEvent(DebugEvent):
    EVENT_TOPIC = 'exception'

    def __init__(self, *args, level='danger', **kwargs):
        super().__init__(*args, level=level, **kwargs)
        self.add_data('script', __file__)
        self.add_data('details', 'Exception occured')
        self.add_data('Exception', traceback.format_exc())


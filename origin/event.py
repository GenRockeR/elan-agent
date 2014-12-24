from origin.neuron import Dendrite
import datetime, sys

class Event():
    def __init__(self, event_type, source, level='info', timestamp=None, dendrite=None):
        if dendrite is None:
            dendrite = Dendrite('events')
        if timestamp is None:
            timestamp = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch
        
        self.type = event_type
        self.source = source
        self.level = level
        self.timestamp = timestamp
        self.data = []
        self.dentrite = dendrite
        
    def add_data(self, key, value, data_type=None):
        if data_type is None:
            item = (key,value)
        else:
            item = (key, value, data_type)
        self.data.append(item)
        
        return self
    
    def notify(self):
        self.dendrite.post('event', {
                'type':        self.type,
                'source':      self.source,
                'level':       self.level,
                'timestamp':   self.timestamp,
                'data':        self.data,
        })

class InternalEvent(Event):
    def __init__(self, *args, **kwargs):
        super(InternalEvent, self).__init__('internal', *args, **kwargs)

class ExceptionEvent(InternalEvent):
    def __init__(self, *args, **kwargs):
        super(ExceptionEvent, self).__init__(*args, **kwargs)
        self.add_data('script', __file__)
        self.add_data('details', 'Exception occured')
        self.add_data('Exception', sys.exc_info()[0])
    

from datetime import timedelta, datetime
from unittest.mock import MagicMock
import unittest

from elan.event import Event, ExceptionEvent, DebugEvent
from elan.neuron import Dendrite


class EventTest(unittest.TestCase):
    'These tests require a MQTT broker'

    def test_Event_timestamp(self):
        event = Event(event_type='test_event', source='test')
        self.assertAlmostEqual(datetime.utcfromtimestamp(event.timestamp), datetime.utcnow(), delta=timedelta(seconds=2), msg='timestamp set to current epoch')

        event = Event(event_type='test_event', source='test', timestamp=1234)
        self.assertEqual(event.timestamp, 1234)

    def test_DebugEvent(self):
        event = DebugEvent(event_type='test_event', source='test')
        self.assertEqual(event.level, 'internal', 'Debug event has "internal" level by default')

    def test_ExceptionEvent(self):
        event = ExceptionEvent(event_type='test_event', source='test')
        self.assertTrue(event.data)

    def test_EventDataType(self):
        event = Event(event_type='test_event', source='test')

        event.add_data(key='test', value='test 1', data_type='str')
        event.add_data(key='test', value='test 2')

        self.assertEqual(event.data[0]['type'], 'str')
        self.assertNotIn('type', event.data[1])

    def test_notify_without_Dendrite(self):
        Dendrite.publish_single = MagicMock()

        event = Event(event_type='test_event', source='test')
        event.notify()

        self.assertEqual(Dendrite.publish_single.call_count, 1)

    def test_notify_with_Dendrite(self):
        Dendrite = MagicMock()

        event = Event(event_type='test_event', source='test', dendrite=Dendrite())
        event.notify()

        self.assertEqual(event.dendrite.publish.call_count, 1)

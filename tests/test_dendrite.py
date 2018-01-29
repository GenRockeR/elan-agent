from unittest.mock import patch, Mock
from uuid import uuid4
import concurrent.futures
import json
import time
import unittest

from paho.mqtt import client

from origin.neuron import Dendrite, RequestTimeout, RequestError


class DendriteTest(unittest.TestCase):
    'These tests require a MQTT broker'

    def setUp(self):
        self.dendrite = Dendrite()
        self.mqtt = client.Client()
        self.mqtt.connect(Dendrite.MQTT_HOST, Dendrite.MQTT_PORT)

    def tearDown(self):
        self.dendrite.finish()
        self.mqtt.disconnect()

    def test_publish(self):
        topic1 = 'test/topic1'
        topic2 = 'test/topic2'
        msg1 = dict(test='OK')

        self.mqtt.subscribe(topic1)
        self.mqtt.subscribe(topic2)

        future = concurrent.futures.Future()

        def on_message(client, userdata, message):
            future.set_result(message)

        self.mqtt.on_message = on_message
        self.mqtt.loop_start()

        time.sleep(1)
        self.dendrite.publish(topic1, msg1)

        msg = future.result(2)

        self.assertEqual(json.loads(msg.payload.decode()), msg1)
        self.assertEqual(msg.topic, topic1)

        msg2 = dict(test=dict(OK='ok'), OK='ok')

        results = []
        future = concurrent.futures.Future()

        def on_message2(client, userdata, message):
            results.append(message)
            if len(results) == 3:
                future.set_result(True)

        self.mqtt.on_message = on_message2

        self.dendrite.publish(topic2, msg1)
        self.dendrite.publish(topic2, msg2)
        self.dendrite.publish(topic1, msg2)

        future.result(2)

        self.assertEqual(json.loads(results[0].payload.decode()), msg1)
        self.assertEqual(results[0].topic, topic2)

        self.assertEqual(json.loads(results[1].payload.decode()), msg2)
        self.assertEqual(results[1].topic, topic2)

        self.assertEqual(json.loads(results[2].payload.decode()), msg2)
        self.assertEqual(results[2].topic, topic1)

    def test_subscribe(self):
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        future = concurrent.futures.Future()

        def get_msg(msg, topic):
            future.set_result({ 'msg': msg, 'topic': topic})

        self.dendrite.subscribe(topic1, get_msg)

        time.sleep(1)

        self.mqtt.publish(topic1, json.dumps(msg1))

        result = future.result(2)
        self.assertEqual(result, {'msg': msg1, 'topic': topic1})

    def test_subscribe_1arg(self):
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        future = concurrent.futures.Future()

        def get_msg(msg):
            future.set_result(msg)

        self.dendrite.subscribe(topic1, get_msg)

        time.sleep(1)

        self.mqtt.publish(topic1, json.dumps(msg1))

        result = future.result(2)

        self.assertEqual(result, msg1)

    def test_subscribe_1arg_method(self):
        topic1 = 'test/topic1'
        msg1 = dict(test='OK', msg=1)

        future = concurrent.futures.Future()

        class Dummy:

            def get_msg(self, msg):
                future.set_result(msg)

        d = Dummy()
        self.dendrite.subscribe(topic1, d.get_msg)

        time.sleep(1)

        self.mqtt.publish(topic1, json.dumps(msg1))

        result = future.result(2)

        self.assertEqual(result, msg1)

    def test_call_and_provide(self):

        def cb(data):
            return 'Test OK: ' + data

        service = 'test/fct'
        self.dendrite.provide('test/fct', cb)

        params = str(uuid4())

        result = self.dendrite.call(service, params)

        self.assertEqual(result, 'Test OK: ' + params)

    def test_call_and_provide_exception(self):

        def cb(data):
            raise RequestError({'something': 'happened'}, 'Error: Something Happened !')

        service = 'test/fct2'
        self.dendrite.provide('test/fct2', cb)

        with self.assertRaises(RequestError) as cm:
            self.dendrite.call(service, {})
        self.assertEqual(cm.exception.error_str, 'Error: Something Happened !')
        self.assertEqual(cm.exception.errors, {'something': 'happened'})

    def test_get(self):
        dummy = str(uuid4())
        self.dendrite.publish('test/get', dummy, retain=True)
        result = self.dendrite.get('test/get')

        self.assertEqual(result, dummy)

        Dendrite.publish_single('test/get', retain=True)

        time.sleep(1)

        with self.assertRaises(RequestTimeout):
            self.dendrite.get('test/get')

    def test_get_from_cb(self):
        get_result = []
        dummy = str(uuid4())

        def cb(data):
            self.dendrite.publish('test/get', dummy, retain=True)
            get_result.append(self.dendrite.get('test/get'))
            return 'Test OK: ' + data

        service = 'test/fct'
        self.dendrite.provide('test/fct', cb)

        params = str(uuid4())

        call_result = self.dendrite.call(service, params, timeout=5)

        self.assertEqual(call_result, 'Test OK: ' + params)
        self.assertEqual(get_result[0], dummy)

        Dendrite.publish_single('test/get', retain=True)

    def test_subscribe_cb_exception_catch(self):
        event_instance = Mock()
        with patch('origin.event.ExceptionEvent', return_value=event_instance) as ExceptionEventMock:
            topic1 = 'test/topic1'
            msg1 = dict(test='OK', msg=1)

            future = concurrent.futures.Future()

            def get_msg(msg, topic):
                future.set_result({ 'msg': msg, 'topic': topic})
                raise KeyError("foo")

            self.dendrite.subscribe(topic1, get_msg)

            time.sleep(1)

            self.mqtt.publish(topic1, json.dumps(msg1))

            result = future.result(2)

        ExceptionEventMock.assert_called_with(source='dendrite-subscribe-cb')
        event_instance.notify.assert_called_once_with()


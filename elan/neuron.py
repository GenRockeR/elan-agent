import concurrent.futures
import inspect
import json
import re
import threading
import time
import uuid

from paho.mqtt import publish
import serialized_redis

import paho.mqtt.client as mqtt

DENDRITE_COMMANDS = 'dendrite:commands'
DENDRITE_ANSWERS = 'dendrite:answers'

AXON_ANSWERS = 'axon:answers:{name}'
AXON_CALLS = 'axon:calls:{name}'

CALL_TIMEOUT = 60  # seconds
SYNC_CALL_TIMEOUT = 40  # seconds


def wait_for_synapse_ready(synapse=None, verbose=False):
    if synapse is None:
        synapse = Synapse()

    count = 1
    while not is_synapse_ready(synapse):
        if verbose and count == 1:
            print('Redis not ready, waiting...')
        count += 1
        if count == 10:
            count = 1
        time.sleep(1)


def is_synapse_ready(synapse=None):
    if synapse is None:
        synapse = Synapse()
    try:
        return bool(synapse.ping())
    except serialized_redis.redis.ConnectionError:
        return False


class Synapse(serialized_redis.JSONSerializedRedis):
    '''
        Wrapper to Redis that JSON en/decodes all values
    '''
    pool = serialized_redis.redis.ConnectionPool(decode_responses=True)

    def get_unique_id(self, path='synapse:unique_id'):
        '''
            Return a unique integer ID (incremented at each call)
            optional path where to store last id.
        '''
        return self.incr(path)

    def __init__(self):
        super(Synapse, self).__init__(connection_pool=self.pool)
        self.pipe = self.pipeline()


class ConnectionFailed():
    pass


class RequestTimeout(Exception):

    def __init__(self, details):
        super().__init__(details)


class RequestError(Exception):
    '''Exception to indicate an error occured during RPC request. This can be raised in provide callback, the caller will receive it.
       Note: errors should be json serializable by json.dumps
    '''

    def __init__(self, errors=None, error_str=''):
        '''
        errors can be any JSON serializale object. error_str should be a a string. If not given, defaults to str(errors)
        errors should be used by apps that know how it is formated and should handle the use of error_str when errors not provided.
        '''
        if not errors and not error_str:
            raise ValueError('"errors" or "error_str" should be set')
        if not isinstance(error_str, str):
            raise ValueError('"error_str" should be a string')

        super().__init__(errors, error_str)

    @property
    def errors(self):
        return self.args[0]

    @property
    def error_str(self):
        return self.args[1] or str(self.args[0])


class  Dendrite(mqtt.Client):
    '''
        Dendrite is used to retrieve configuration (and configuration updates), declare what RPC are processed by the calling module and make RPC calls
        Instantiate class, call subscribe, subscribe_conf, publish, publish_conf, call or provide with topic/service and callback. callback receive message and optionnaly topic.

        Use class method publish_single for a single publish. This will connect, publish and disconnect and will be blocking.

        When using instance:
        - all callbacks are executed in an other thread.
        - calls are non blocking (publish will happen in another thread)

    '''
    CONF_TOPIC_PREFIX = 'conf/'
    CACHE_PREFIX = 'cache:'

    SERVICE_REQUESTS_TOPIC_PATTERN = 'service/requests/{service}'
    SERVICE_ANSWERS_TOPIC_PATTERN = 'service/answers/{service}/{request_id}'

#     RPC_REQUESTS_PATH_PREFIX = 'rpc/requests/'
#     RPC_ANSWERS_PATH_PREFIX  = 'rpc/answers/'

    MQTT_HOST = '127.0.0.1'
    MQTT_PORT = 1883

    def __init__(self):
        self.topics = set()
        super().__init__()

        self.connect_async(self.MQTT_HOST, self.MQTT_PORT)
        self.loop_start()

    @classmethod
    def publish_single(cls, topic, data=None, retain=False):
        if data is not None:
            data = json.dumps(data)
        return publish.single(topic, data, qos=1, retain=retain, hostname=cls.MQTT_HOST, port=cls.MQTT_PORT)

    @classmethod
    def publish_conf_single(cls, topic, data=None, retain=True):
        return cls.publish_single(cls.CONF_TOPIC_PREFIX + topic, data, retain=retain)

    def finish(self):
        self.disconnect()
        self.loop_stop()

    def on_connect(self, mqttc, obj, flags, rc):
        if self.topics:
            self._subscribe([ (topic, 1) for topic in self.topics ])

    def _call_fn_with_good_arg_nb(self, fn, *args):
        nb_args = len(inspect.signature(fn).parameters)
        args = args[:nb_args]

        return fn(*args)

    def _run_and_notifify_exceptions(self, fn, *args, source='dendrite'):
        from . import  event
        try:
            self._call_fn_with_good_arg_nb(fn, *args)
        except:
            event.ExceptionEvent(source=source).notify()

    def _subscribe_cb_wrapper(self, fn):

        def wrapper(mqttc, userdata, message):
            if message.payload:
                data = json.loads(message.payload.decode())
            else:
                data = None
            # start in a Thread so we can call again some function like call and get from callbacks
            # (or else they are all run in same thread (paho mqtt impementation),
            # so any other callback is not called until cb finished)
            task = threading.Thread(target=self._run_and_notifify_exceptions, args=(fn, data, message.topic), kwargs={'source': 'dendrite-subscribe-cb'})
            task.start()

        return wrapper

    def _subscribe_conf_cb_wrapper(self, fn):

        def wrapper(data, topic):
            subtopic = topic[len(self.CONF_TOPIC_PREFIX):]
            return self._call_fn_with_good_arg_nb(fn, data, subtopic)

        return wrapper

    def _provide_cb_wrapper(self, fn):

        def wrapper(data, topic):
            m = re.match(self.SERVICE_REQUESTS_TOPIC_PATTERN.format(service='(?P<service>.+)') + '$', topic)
            answer = {}
            try:
                answer['result'] = self._call_fn_with_good_arg_nb(fn, data['request'], m.group('service'))
            except RequestError as e:
                answer['errors'] = e.errors
                answer['error_str'] = e.error_str
            except Exception as e:
                answer['error_str'] = repr(e)
            self.publish(self.SERVICE_ANSWERS_TOPIC_PATTERN.format(request_id=data['id'], service=m.group('service')), answer)

        return wrapper

    def subscribe(self, topic, cb):
        self.topics.add(topic)
        self.message_callback_add(topic, self._subscribe_cb_wrapper(cb))
        return self._subscribe(topic)

    def _subscribe(self, topic):
        return super().subscribe(topic, qos=1)

    def unsubscribe(self, topic):
        self.topics.discard(topic)
        self.message_callback_remove(topic)
        return super().unsubscribe(topic)

    def subscribe_conf(self, topic, cb):
        return self.subscribe(self.CONF_TOPIC_PREFIX + topic, self._subscribe_conf_cb_wrapper(cb))

    def publish(self, topic, data=None, retain=False):
        '''
            publish message (JSON encoded) to topic.
            By default, does not ask to retain message.
            If data not provided or None, empty message sent.
        '''
        if data is not None:
            data = json.dumps(data)
        return super().publish(topic, data, retain=retain, qos=1)

    def publish_conf(self, path, message, retain=True):
        return self.publish(self.CONF_TOPIC_PREFIX + path, message, retain=retain)

    def provide(self, service, cb):
        '''
        provides a service RPC style by running callback cb on call.
        callback may raise RequestError to indicate an error that will be sent back to caller. error must be json serializable.
        '''
        return self.subscribe(self.SERVICE_REQUESTS_TOPIC_PATTERN.format(service=service), self._provide_cb_wrapper(cb))

    def unprovide(self, service):
        return self.unsubscribe(self.SERVICE_REQUESTS_TOPIC_PATTERN.format(service=service))

    def get(self, topic, timeout=1):
        '''
        Get first message from topic
        '''
        future = concurrent.futures.Future()

        def cb(result):
            future.set_result(result)

        self.subscribe(topic, cb)

        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError:
            raise RequestTimeout('Could not retrieve first value of "{topic}" within {timeout} seconds'.format(topic=topic, timeout=timeout))
        finally:
            if topic not in self.topics:
                self.unsubscribe(topic)

    def get_conf(self, topic, timeout=1):
        'get configuration value. This relies on `run_conf_cacher` to be executed'
        synapse = Synapse()
        try:
            return synapse.get(self.CACHE_PREFIX + self.CONF_TOPIC_PREFIX + topic)
        except serialized_redis.redis.ConnectionError as e:
            raise ConnectionFailed(e)

    def call(self, service, data=None, timeout=30):
        '''
        RPC request to service, returns result or raises RequestError or RequestTimeout.
        This should not be called in async function as it will block the event loop.
        However it can be safely called from Thread Executor or when not event loop is running (will run it for a short while)
        '''
        request_id = str(uuid.uuid4())
        future = concurrent.futures.Future()

        def cb(result):
            future.set_result(result)

        self.subscribe(self.SERVICE_ANSWERS_TOPIC_PATTERN.format(service=service, request_id=request_id), cb)
        # normally, we should wait for on_subscribe callback to make sure we have subscribed before sending request,
        #  but let's assume that if mosquitto receives the publish, it has already received the subscribe...
        self.publish(self.SERVICE_REQUESTS_TOPIC_PATTERN.format(service=service), {'request': data, 'id': request_id})
        try:
            answer = future.result(timeout)
        except concurrent.futures.TimeoutError:
            raise RequestTimeout('Call to "{service}" timed out after {timeout} seconds'.format(service=service, timeout=timeout))
        finally:
            self.unsubscribe(self.SERVICE_ANSWERS_TOPIC_PATTERN.format(service=service, request_id=request_id))

        if 'errors' in answer or 'error_str' in answer:
            raise RequestError(answer.get('errors', None), answer.get('error_str', ''))

        return answer['result']

    def wait_complete(self, timeout=None):
        '''
        Block until timeout or disconnect called
        '''
        self._thread.join(timeout)

    def run_conf_cacher(self):
        '''
        will run configuration cacher to store configuration in Redis
        '''
        synapse = Synapse()

        def cache_conf(data, path):
            synapse.set(self.CACHE_PREFIX + path, data)

        self.subscribe(Dendrite.CONF_TOPIC_PREFIX + '#', cache_conf)
        self.wait_complete()


class ConfObject:
    _dendrite = Dendrite()

    @classmethod
    def count(cls):
        '''
        Count the number of objects the configuration has.
        Assumes the configuration is a list.
        '''
        return len(cls._dendrite.get_conf()(cls.TOPIC) or [])

    @classmethod
    def get_all(cls, **filters):
        '''
        Retrieve the first object that matches all `filters`.
        :param filters: key/value pairs the object should have.
        :returns: a list of instances.
        Assumes the configuration is a list.
        '''
        objects = []
        conf = cls._dendrite.get_conf(cls.TOPIC) or []
        for obj in conf:
            for key, value in filters.items():
                if conf.get(key, None) != value:
                    break
            else:
                # matches all filters
                objects.append(cls(**obj))
        return objects

    @classmethod
    def get(cls, **filters):
        '''
        Retrieve the first object that matches all `filters`.
        :param filters: key/value pairs the object should have.
        :returns: an instance if found or None.
        Assumes the configuration is a list.
        '''
        conf = cls._dendrite.get_conf(cls.TOPIC) or []
        for obj in conf:
            for key, value in filters.items():
                if conf.get(key, None) != value:
                    break
            else:
                # matches all filters
                return cls(**obj)

    def __init__(self, **kwargs):
        for key in kwargs:
            setattr(self, key, kwargs[key])


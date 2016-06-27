import json, datetime, traceback, time
import uuid
import redis
from .. import utils
import inspect
import concurrent.futures
import asyncio
import hbmqtt.client
from signal import SIGTERM

CACHE_PREFIX = 'cache:'

DENDRITE_COMMANDS = 'dendrite:commands'
DENDRITE_ANSWERS = 'dendrite:answers'
 
AXON_ANSWERS = 'axon:answers:{name}'
AXON_CALLS = 'axon:calls:{name}'

CALL_TIMEOUT = 60 # seconds
SYNC_CALL_TIMEOUT = 40 #seconds

def wait_for_synapse_ready():
    started = False
    s = Synapse()
    
    while not started:
        try:
            started = s.ping()
        except redis.exceptions.ConnectionError:
            time.sleep(1)


class Synapse(redis.StrictRedis):
    '''
        Wrapper to Redis that JSON en/decodes all values
    '''
    pool = redis.ConnectionPool(decode_responses=True)
    
    def get_unique_id(self, path='synapse:unique_id'):
        '''
            Return a unique integer ID (incremented at each call)
            optional path where to store last id.
        '''
        return self.incr(path)

    def pipeline(self, transaction=True, shard_hint=None):
        return SynapsePipeline(
            self.connection_pool,
            self.response_callbacks,
            transaction,
            shard_hint)

    def __init__(self):
        super(Synapse, self).__init__(connection_pool=self.pool)
        
        # Decorate response_callbacks to parse Json output
        FROM_JSON_CALLBACKS = {
                'GET':           self.parse_single_object,
                'HGETALL':       self.parse_hgetall,
                'HGET':          self.parse_single_object,
                'HKEYS':         self.parse_list,
                'HVALS':         self.parse_list,
                'SMEMBERS':      self.parse_smembers, 
                'ZRANGE':        self.parse_zrange,
                'ZRANGEBYSCORE': self.parse_zrange,
                'LRANGE':        self.parse_list,
                'LPOP':          self.parse_single_object,
                'BLPOP':         self.parse_bpop,
                'BRPOP':         self.parse_bpop,
        }
        
        def decorate_callback(fn, otherFn):
            def newFn(response, **options):
                new_response = fn(response, **options)
                return otherFn(new_response, **options)
            return newFn

        for cmd in FROM_JSON_CALLBACKS:
            if cmd in self.response_callbacks:
                self.response_callbacks[cmd] = decorate_callback(self.response_callbacks[cmd], FROM_JSON_CALLBACKS[cmd]) 
            else:
                self.response_callbacks[cmd] = FROM_JSON_CALLBACKS[cmd]

        self.pipe = self.pipeline()

    def parse_single_object(self, response, **options):
        if response == None:
            return None
        return json.loads(response)

    def set(self, key, value, *args, **kwargs):
        ''' JSON encodes object and stores it '''
        return super(Synapse, self).set( key, json.dumps(value, sort_keys=True), *args, **kwargs )
    
    def sget(self, key):
        '''
        Smart get: like get but smarter, returns good type:
            if redis hash, returns python dict
            if redis array, returns python array
            if redis set, return python set
            if redis string, returns python string
        '''
        if not self.exists(key):
            return None
        return {
                   'set': self.smembers,
                   'hash': self.hgetall,
                   'string': self.get,
                   'list': self.lmembers,
               }[self.type(key)](key)
        
#   NOT TESTED AT ALL !!! TODO: test this !
    def sset(self, key, value):
        '''
        Smart set: like set but smarter, sets good type:
            if python dict, uses redis hash
            if python array, uses redis array 
            if python set, uses redis set 
            otherwise uses redis string
        '''
        with self.pipeline() as pipe:
            pipe.delete(key)
     
            value_type = type(value).__name__
            if value_type == 'set':
                pipe.sadd(key, *list(json.dumps(v, sort_keys=True) for v in value) )
            elif value_type == 'list':
                pipe.rpush(key, *list(json.dumps(v, sort_keys=True) for v in value) )
            elif value_type == 'dict':
                pipe.hmset(key, {k: json.dumps(v, sort_keys=True) for k,v in value.items()})
            else:
                pipe.set(key, json.dumps(value, sort_keys=True))
     
            pipe.execute()

    # Hashes: fields can be objects
    def parse_hgetall(self, response, **options):
        return { json.loads(k): json.loads(v) for k, v in response.items() }

    def hget(self, key, field):
        return super(Synapse, self).hget(key, json.dumps(field, sort_keys=True))

    def hmget(self, key, *fields):
        return super(Synapse, self).hmget(key, *list(json.dumps(field, sort_keys=True) for field in fields))

    def hexists(self, key, field):
        return super(Synapse, self).hexists(key, json.dumps(field, sort_keys=True))

    def hincrby(self, key, field, increment):
        return super(Synapse, self).hincrby(key, json.dumps(field, sort_keys=True), increment)

    def hincrbyfloat(self, key, field, increment):
        return super(Synapse, self).hincrbyfloat(key, json.dumps(field, sort_keys=True), increment)

    def hdel(self, key, *fields):
        return super(Synapse, self).hdel(key, *list(json.dumps(field, sort_keys=True) for field in fields) )

    def hset(self, key, field, value):
        return super(Synapse, self).hset(key, json.dumps(field, sort_keys=True), json.dumps(value, sort_keys=True))

    def hsetnx(self, key, field, value):
        return super(Synapse, self).hsetnx(key, json.dumps(field, sort_keys=True), json.dumps(value, sort_keys=True))

    def hmset(self, key, mapping):
        return super(Synapse, self).hset( key, ([ json.dumps(field, sort_keys=True), json.dumps(value, sort_keys=True)] for field, value in mapping) )

    # Sets
    def sismember(self, key, value):
        return super(Synapse, self).sismember(key, json.dumps(value, sort_keys=True))

    def sadd(self, key, *args):
        return super(Synapse, self).sadd(key, *list(json.dumps(v, sort_keys=True) for v in args))

    def srem(self, key, *args):
        return super(Synapse, self).srem(key, *list(json.dumps(v, sort_keys=True) for v in args))
        
    def smembers(self, *args, **kwargs):
        return set(super(Synapse, self).smembers(*args, **kwargs))

    def smembers_as_list(self, *args, **kwargs):
        return super(Synapse, self).smembers(*args, **kwargs)

    def parse_smembers(self, response, **options):
        # return list as members may not be hashable, smember fct will turn in into set. 
        # caller should call smembers_as_list if it is known that members may be unhashable and deal with a list instead of a set
        return [json.loads(v) for v in response] 

    # oredered sets
    def zadd(self, key, *args):
        json_args = []

        a=iter(args)
        for score, value in zip(a,a):
            json_args.append( score )
            json_args.append( json.dumps(value, sort_keys=True) )
        
        return super(Synapse, self).zadd(key, *json_args)

    def zrem(self, key, *args):
        return super(Synapse, self).zrem(key, *list(json.dumps(v, sort_keys=True) for v in args))
        
    def zmembers(self, key):
        return self.zrange(key, 0, -1)

    def zscore(self, key, value):
        return super(Synapse, self).zscore(key, json.dumps(value, sort_keys=True))

    def parse_zrange(self, response, **options):
        if options.get('withscores', False):
            return [(json.loads(v[0]), v[1]) for v in response]
        else:
            return [json.loads(v) for v in response]

    # Lists
    def lmembers(self, key):
        return self.lrange(key, 0, -1)
    
    def parse_list(self, response, **options):
        return [json.loads(v) for v in response]

    def lpush(self, key, *args):
        return super(Synapse, self).lpush(key, *list(json.dumps(v, sort_keys=True) for v in args))
    
    def parse_bpop(self, response, **options):
        if response == None:
            return None
        return (response[0], json.loads(response[1]))

    def rpush(self, key, *args):
        return super(Synapse, self).rpush(key, *list(json.dumps(v, sort_keys=True) for v in args))
    
    def rpop(self, key):
        data = super(Synapse, self).rpop(key)
        if data == None:
            return None
        return json.loads(data)

    def publish(self, channel, msg):
        return super(Synapse, self).publish(channel, json.dumps(msg, sort_keys=True))

    def type(self, key):
        return super(Synapse, self).type(key)
    
    def pubsub(self):
        return super(Synapse, self).pubsub()

class SynapsePipeline(redis.client.BasePipeline, Synapse):
    "Pipeline for the Synapse class"
    pass



class TimeOutException(Exception):
    pass

class  Dendrite():
    '''
        Dendrite is used to retrieve configuration (and configuration updates), declare what RPC are processed by this modeule and make RPC calls
        Instantiate class, call subscribe_conf or provide with path and callback. callback receive path and message. 
        
        Callbacks can be sync or async. sync callbacks are run in an executor.
        Parameter of callbacks are:
        - conf/message
        - path 
        
        (un)subscribe(_conf), (un)provide and publish(_conf) functions can be called from sync and async functions
    '''
    CONF_PATH_PREFIX = 'conf/'
    PROVIDE_REQUESTS_PATH_PREFIX = 'provided/requests/'
    PROVIDE_ANSWERS_PATH_PREFIX  = 'provided/answers/'
    
    def __init__(self, *, mqtt_url='mqtt://127.0.0.1', loop=None):
        self._connection = None
        if loop:
            self._loop = loop
        else:
            self._loop = asyncio.get_event_loop()
        
        self._loop.add_signal_handler(SIGTERM, self.finish)
        
        self._connection = hbmqtt.client.MQTTClient(config={'auto_reconnect': True, 'reconnect_retries': 100000000, 'reconnect_max_interval': 10}, loop=self._loop)
        self._loop.run_until_complete( self._connection.connect(mqtt_url, cleansession=True) )
        
        self.subscribe_cb = {}
        
        self.listen_task = None
        self.tasks = set()
    
    def _cleanup_tasks(self, tasks=None):
        if tasks is None:
            tasks = self.tasks
        to_remove = set()
        for task in tasks:
            if task.done():
                to_remove.add(task)
        for task in to_remove:
            tasks.remove(task)

    @property
    def running(self):
        return self._loop.is_running()
    
    def run(self, tasks=None, timeout=None):
        '''
        Run pending tasks on event loop like subscribe and start listening to messages in case of provide or subscribe.
        This starts the asyncio event loop  until all pending tasks are finished. In case of subscribe and provide, it runs for ever (listen task never ends until unsubscribe)
        '''
        if tasks is None:
            tasks = self.tasks
        else:
            tasks = set(tasks)
        try:
            while tasks:
                start = time.time()
                self._loop.run_until_complete( asyncio.wait([asyncio.wrap_future(task) for task in tasks], timeout=timeout) ) # tasks here are concurrent.futures.Future, not asyncio.Future
                self._cleanup_tasks(tasks)
                if timeout:
                    timeout = float(timeout) - (time.time() - start)
                    if timeout < 0:
                        break
                    
        except asyncio.TimeoutError:
            raise TimeOutException('Run timed out')

    def finish(self):
        self.add_task( self._finish() ) 
    
    async def _finish(self):
        if self.listen_task:
            self.listen_task.cancel()
            asyncio.wait(self.listen_task)
        
        for topic in self.subscribe_cb.keys():
            await self._unsubscribe(topic)

        await self._connection.disconnect()
                
    async def listen_messages(self):
        while True:
            try:
                message = await self._connection.deliver_message()
                # Create a task so we can receive more message meanwhile instead of waiting for the processing to finish
                self.add_task( self.process_message(message) )
            except hbmqtt.client.ClientException as e:
                print('Error receiving MSG', e)
            
        
            
    async def process_message(self, message):
            msg = json.loads(message.data.decode())
            topic = message.topic

            
            cb = self.subscribe_cb.get(topic, None)
            if cb:
                if topic.startswith(self.PROVIDE_REQUESTS_PATH_PREFIX):
                    path = topic[len(self.PROVIDE_REQUESTS_PATH_PREFIX):]
                    correlation_id = msg['correlation_id']
                    data = msg['message']
                elif topic.startswith(self.CONF_PATH_PREFIX):
                    path = topic[len(self.CONF_PATH_PREFIX):]
                    data = msg
                else:
                    path = topic
                    data = msg

                # Accept to send only data without topic
                cb_args_nb = len(inspect.signature(cb).parameters)
                cb_is_method = inspect.ismethod(cb)
                if (cb_args_nb == 1 and not cb_is_method) or (cb_args_nb == 2 and cb_is_method):
                    result = await self._call_fn(cb, data)
                else: 
                    result = await self._call_fn(cb, data, path)

                if topic.startswith(self.PROVIDE_REQUESTS_PATH_PREFIX):
                    # Send back answer
                    await self._connection.publish(
                                 self.PROVIDE_ANSWERS_PATH_PREFIX + correlation_id,
                                 json.dumps(result).encode(),
                                 hbmqtt.client.QOS_1
                    )
    
    async def _call_fn(self, fn, *args, delay=0):
        if delay:
            await asyncio.sleep(delay, loop=self._loop)
        # Accepts coroutings (args will be ignored), coroutines functions and synchronous functions
        if asyncio.iscoroutinefunction(fn):
            coro = fn(*args)
        elif asyncio.iscoroutine(fn):
            coro = fn
        else:
            coro = self._loop.run_in_executor(None, fn, *args)
        
        return await coro
                    
    def add_task(self, fn, *args, delay=0):
        '''
        Thread safe function to schedule a task to async queue. task will be added to list of task waited for when using run().
        Argument can be a function (will be wrapped in run_in_executor), a coroutine (args will be ignored) or a coroutine function.
        with keyword delay, the task will be delayed delay seconds before running
        returns a concurent.future.Future
        '''
        
        task = asyncio.run_coroutine_threadsafe( self._call_fn(fn, *args, delay=delay), loop=self._loop )
        self.tasks.add( task )
        self._cleanup_tasks()
        return task

    def subscribe(self, topic, cb):
        return self.add_task(self._subscribe(topic, cb))
    
    async def _subscribe(self, topic, cb):
        if not self.listen_task or self.listen_task.done():
            self.listen_task = self.add_task( self.listen_messages() )
        self.subscribe_cb[topic] = cb
        await self._connection.subscribe([(topic, hbmqtt.client.QOS_1)])
        
    def unsubscribe(self, topic):
        return self.add_task(self._unsubscribe(topic))

    async def _unsubscribe(self, topic):
        self.subscribe_cb.pop(topic)
        await self._connection.unsubscribe([topic])
        if not self.subscribe_cb and self.listen_task:
            self.listen_task.cancel()
    
    def subscribe_conf(self, path, cb):
        return self.subscribe('conf/' + path, cb)
    
    async def _publish(self, topic, message, retain=False):
        await self._connection.publish(topic, json.dumps(message).encode(), qos=hbmqtt.client.QOS_1, retain=retain)
    
    def publish(self, topic, message, retain=False, auto_run=True):
        '''
            publish message to topic.
            By default, does not ask to retain message and if dendrite not running, will run until this publish has been done (other tasks may run also)
        '''
        task = self.add_task( self._publish(topic, message, retain=retain) )
        if auto_run and not self.running:
            self.run([task])

    def publish_conf(self, path, message, auto_run=True):
        return self.publish(self.CONF_PATH_PREFIX+path, message, retain=True, auto_run=auto_run)
    
    def provide(self, topic, cb):
        '''
        provides a service RPC style by running callback cb on call.
        '''
        return self.subscribe(self.PROVIDE_REQUESTS_PATH_PREFIX+topic, cb)

    def unprovide(self, path):
        return self.unsubscribe(self.PROVIDE_REQUESTS_PATH_PREFIX+path)
    
    def sync_call(self, path, data=None, timeout=30):
        '''
        sync RPC request to path, returns result or raises TimeOutException.
        This should not be called in async function as it will block the event loop.
        However it can be safely called from Thread Executor or when not event loop is running (will run it for a short while)
        '''
        correlation_id = str(uuid.uuid4())
        future = concurrent.futures.Future()
        
        def cb(result):
            future.set_result(result)
            self.unsubscribe(self.PROVIDE_ANSWERS_PATH_PREFIX + correlation_id)
            
        sub_task = self.subscribe(self.PROVIDE_ANSWERS_PATH_PREFIX + correlation_id, cb)
        if self.running:
            sub_task.result()# wait for result
        else:
            self.run([sub_task])
        self.publish(self.PROVIDE_REQUESTS_PATH_PREFIX + path, {'correlation_id': correlation_id, 'message': data})
        try:
            if self.running:
                return future.result(timeout)
            else:
                self.run([future], timeout=timeout)
                return future.result(0)
        except concurrent.futures.TimeoutError:
            raise TimeOutException('Call to {path} timed out after {timeout} seconds'.format(path=path, timeout=timeout))
    
    async def async_call(self, path, data=None, timeout=30):
        '''
            RPC call to path, returns result or raises TimeOutException.
        '''
        correlation_id = str(uuid.uuid4())
        future = asyncio.Future()
        
        def cb(result):
            future.set_result(result)
            self.unsubscribe(self.PROVIDE_ANSWERS_PATH_PREFIX + correlation_id)
            
        self.subscribe(self.PROVIDE_ANSWERS_PATH_PREFIX + correlation_id, cb)
        self.publish(self.PROVIDE_REQUESTS_PATH_PREFIX + path, {'correlation_id': correlation_id, 'message': data})
        try:
            return await asyncio.wait_for(future, timeout)
        except concurrent.futures.TimeoutError:
            raise TimeOutException('Call to {path} timed out after {timeout} seconds'.format(path=path, timeout=timeout))
        
    
    
    
    
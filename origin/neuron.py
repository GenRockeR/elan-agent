import tornado.ioloop, tornado.websocket, tornado.gen, tornado.options
import json, datetime, traceback
import tornadoredis
import redis

CACHE_PREFIX = 'cache:'

SYNAPSE_COMMANDS = 'synapse:commands'
SYNAPSE_ANSWERS = 'synapse:answers'
 
AXON_ANSWERS = 'axon:answers:{name}'
AXON_CALLS = 'axon:calls:{name}'


class Synapse(redis.StrictRedis):
    '''
        Wrapper to Redis that JSON en/decodes all values
    '''
    # REDIS: Wrapper for redis connection that encodes and decodes object using JSON
    def __init__(self):
        super(Synapse, self).__init__(decode_responses=True)

    def get(self, key):
        ''' returns JSON decoded object in key '''
        data = super(Synapse, self).get(key)
        if data == None:
            return None
        return json.loads(data)
    def set(self, key, value):
        ''' JSON encodes object and stores it '''
        return super(Synapse, self).set( key, json.dumps(value, sort_keys=True) )
    
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
                pipe.sadd(key, *(json.dumps(v, sort_keys=True) for v in value) )
            elif value_type == 'list':
                pipe.rpush(key, *(json.dumps(v, sort_keys=True) for v in value) )
            elif value_type == 'dict':
                pipe.hmset(key, {k: json.dumps(v, sort_keys=True) for k,v in value.items()})
            else:
                pipe.set(key, json.dumps(value, sort_keys=True))
     
            pipe.execute()

    # Hashes
    def hgetall(self, key):
        return { k: json.loads(v) for k, v in super(Synapse, self).hgetall(key).items() }

    def hget(self, key, field):
        data = super(Synapse, self).hget(key, field)
        if data == None:
            return None
        return json.loads(data)

    def hset(self, key, field, value):
        return super(Synapse, self).hset(key, field, json.dumps(value, sort_keys=True))

    # Sets
    def sismember(self, key, value):
        return super(Synapse, self).sismember(key, json.dumps(value, sort_keys=True))

    def sadd(self, key, *args):
        super(Synapse, self).sadd(key, *(json.dumps(v, sort_keys=True) for v in args))

    def srem(self, key, *args):
        super(Synapse, self).srem(key, *(json.dumps(v, sort_keys=True) for v in args))
        
    def smembers(self, key):
        return set(json.loads(v) for v in super(Synapse, self).smembers(key))

    # oredered sets
    def zadd(self, key, *args):
        super(Synapse, self).zadd(key, *(json.dumps(v, sort_keys=True) for v in args))

    def zrem(self, key, *args):
        super(Synapse, self).zrem(key, *(json.dumps(v, sort_keys=True) for v in args))
        
    def zmembers(self, key):
        return set(json.loads(v) for v in super(Synapse, self).zrange(key, 0 -1))

    def zscore(self, key):
        return super(Synapse, self).zscore(key)
    
    # Lists
    def lmembers(self, key):
        return [json.loads(v) for v in super(Synapse, self).lrange(key, 0, -1)]

    def lpush(self, key, *args):
        super(Synapse, self).lpush(key, *(json.dumps(v, sort_keys=True) for v in args))
    
    def lpop(self, key):
        data = super(Synapse, self).lpop(key)
        if data == None:
            return None
        return json.loads(data)

    def blpop(self, key, timeout = 0):
        data = super(Synapse, self).blpop(key, timeout)
        if data == None:
            return None
        return (data[0], json.loads(data[1]))

    def rpush(self, key, *args):
        super(Synapse, self).rpush(key, *(json.dumps(v, sort_keys=True) for v in args))
    
    def rpop(self, key):
        data = super(Synapse, self).rpop(key)
        if data == None:
            return None
        return json.loads(data)

    def brpop(self, key, timeout = 0):
        data = super(Synapse, self).brpop(key, timeout)
        if data == None:
            return None
        return (data[0], json.loads(data[1]))

    def pipeline(self):
        return super(Synapse, self).pipeline()

    def transaction(self, func, *watches, **kwargs):
        # create a specific pipeline each time...
        return super(Synapse, self).transaction(func, *watches, **kwargs)
    
    def exists(self, key):
        return super(Synapse, self).exists(key)

    def publish(self, channel, msg):
        return super(Synapse, self).publish(channel, json.dumps(msg, sort_keys=True))

    def type(self, key):
        return super(Synapse, self).type(key)
    
    def pubsub(self):
        return super(Synapse, self).pubsub()

    def keys(self, pattern):
        return super(Synapse, self).keys(pattern)


class Dendrite:
    """ Dendrite is the interface to the Central Controller
        
        Subclass this or provide answer_cb and call_cb to constructor.
        
        When subclassing, use add_callback(channel, callback_fn) to listen to other redis queues.
        By default,listens to answer queue and  call queue (that includes the name)
    """
    
    def __init__(self, name, answer_cb=None, call_cb=None):
        self.name = name # self name used when communication with synapse.
        self.channel_cb = [] # 2-tuple of channel, callback
        self.synapse = Synapse()

        def add_self_decorator(fn):
            def wrapper(*args):
                return fn(self, args)
            return wrapper
        
        if answer_cb:
            self.answer_cb = add_self_decorator(answer_cb)
        if call_cb:
            self.call_cb = add_self_decorator(call_cb)

        # add in order, first one higher priority
        self.add_channel(AXON_CALLS.format(name=self.name), self.call_cb)
        self.add_channel(AXON_ANSWERS.format(name=self.name), self.answer_cb)

    def add_channel(self, channel, cb):
        self.channel_cb.append((channel, cb))
    
    def answer_cb(self, path, answer):
        # might as well unsubscribe as we do nothing about it...
        self.unsubscribe(path)
    
    def call_cb(self, path, request):
        # might as well unprovide as we do known what to do with it......
        self.unprovide(path)

    def run_for_ever(self):
        while True:
            channel, data = self.synapse.brpop([item[0] for item in self.channel_cb])
            # Special cases for common channels call and answer 
            if channel == AXON_CALLS.format(name=self.name):
                path = data['path']
                request = data['data']
                answer = self.call_cb(path, request)
                self._send_answer(req_id = data['req_id'], answer = answer)
                
            elif channel == AXON_ANSWERS.format(name=self.name):
                path = data['path']
                answer = data['data']
                self.answer_cb(path, answer)
                
            else:
                self.channel_cb[channel](data)
        
    def get_provided_services(self):
        services = set()
        for path, provider in self.synapse.hgetall('synapse:providers').items():
            if provider == self.name:
                services.add(path)
        return services
        
    # REST
        
    def post(self, path, data):
        '''
            ASynchronious POST
            Implemented via CALL 
        '''
        self.call(path, data)
    
    
    def _send_command(self, **data):
        data['requester'] = self.name
        self.synapse.lpush(SYNAPSE_COMMANDS, data)

    def _send_answer(self, **data):
        self.synapse.lpush(SYNAPSE_ANSWERS, data)

        
    def retrieve(self, path):
        self._send_command(cmd='RETRIEVE', path=path)

    def subscribe(self, path):
        self._send_command(cmd='SUBSCRIBE', path=path)

    def unsubscribe(self, path):
        self._send_command(cmd='SUBSCRIBE', path=path)

    def provide(self, path):
        self._send_command(cmd='PROVIDE', path=path)

    def unprovide(self, path):
        self._send_command(cmd='UNPROVIDE', path=path)

    def call(self, path, data):
        self._send_command(cmd='CALL', path=path, data=data)

    def answer(self, req_id, answer):
        self._send_answer(req_id=req_id, answer=answer)
        
        
        
        
        
        
        
        
        
        
def check_awaited_path(fn):
    def wrapper(axon, path, *args, **kwargs):
        fn(axon, path, *args, **kwargs)
        def check_answered():
            if path in axon.awaited_paths:
                kwargs['force_send'] = True
                wrapper(axon, path, *args, **kwargs)
        tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=axon.RETRY_INTERVAL), check_answered)
        
    return wrapper


class Axon:
    RETRY_INTERVAL = 5 #seconds

    def __init__(self, url='ws://127.0.0.1:8000/ws'):
        self.url = url

        self.synapse = Synapse() # for sync operations
        self.aredis = tornadoredis.Client() # for blocking operations like brpop .... requires json en/decode...
        self.aredis.connect()

        self.awaited_paths = set()
        self.subscriptions = set()

        # open websocket to control center
        self.ws = None
        self._open_cc_ws()
        
        
        # Listen to commands:
        tornado.ioloop.IOLoop.instance().run_sync(self.listen_commands)
    
    @tornado.gen.coroutine
    def listen_commands(self):
        while True:
            data = yield tornado.gen.Task(self.aredis.brpop, [SYNAPSE_ANSWERS, SYNAPSE_COMMANDS])
            try:
                if SYNAPSE_ANSWERS in data:
                    data = json.loads(data[SYNAPSE_ANSWERS])
                    self.process_answer(data['req_id'], data['answer'])
                else:
                    data = json.loads(data[SYNAPSE_COMMANDS])
                    self.process_command(data)
            except:
                print('error occured:', traceback.format_exc() )
                
    def process_answer(self, req_id, answer):
        if self.ws:
            self.ws.write_message('ANSWER {id}\n{answer}'.format(id=req_id, answer=json.dumps(answer)))
              
    def process_command(self, data):
        if data['cmd'] == 'SUBSCRIBE':
            self.synapse.sadd('synapse:subscribers:'+data['path'], data['requester'])
            #reply from cache if available!
            if self.synapse.exists(CACHE_PREFIX + data['path']):
                self._answer_requester( data['requester'], 
                                        data=self.synapse.get(CACHE_PREFIX + data['path']), 
                                        path=data['path'] )
            self._ws_subscribe(data['path'])
        
        elif data['cmd'] == 'RETRIEVE':
            #reply from cache if available!
            if self.synapse.exists(CACHE_PREFIX + data['path']):
                self._answer_requester( data['requester'], 
                                        data=self.synapse.get(CACHE_PREFIX + data['path']), 
                                        path=data['path'] )
            self._ws_retrieve(data['path'])
        
        elif data['cmd'] == 'PROVIDE':
            self.synapse.hset('synapse:providers', data['path'], data['requester'])
            self._ws_provide(data['path'])
        
        elif data['cmd'] == 'UNPROVIDE':
            self.synapse.hdel('synapse:providers', data['path'])
            self._ws_unprovide(data['path'])
          
            
    @check_awaited_path
    def _ws_subscribe(self, path, force_send = False):
        if path not in self.subscriptions or force_send:
            if self.ws:
                self.ws.write_message('SUBSCRIBE ' + path)
            self.subscriptions.add(path)
            self.awaited_paths.add(path)

    @check_awaited_path
    def _ws_retrieve(self, path, force_send = False):
        if path not in self.awaited_paths or force_send:
            if self.ws:
                self.ws.write_message('RETRIEVE ' + path)
            self.awaited_paths.add(path)

    def _ws_provide(self, path, force_send = False):
        if self.ws:
            self.ws.write_message('PROVIDE ' + path)

    def _ws_unprovide(self, path, force_send = False):
        if self.ws:
            self.ws.write_message('UNPROVIDE ' + path)

    
    def _answer_requester(self, requester, **data):    
        self.synapse.lpush(AXON_ANSWERS.format(name=requester), data)
        
    def _open_cc_ws(self):    
        #ioloop.IOLoop.instance().add_future(tornado.websocket.websocket_connect(self.url), self.ws_open_cb)
        tornado.ioloop.IOLoop.instance().add_future(tornado.websocket.websocket_connect(
                tornado.httpclient.HTTPRequest(
                       self.url,
                       headers = { 'Authorization': 'Token 74d6623e97f758efcc3832cae0880bf3f4240d22f1818767fe7f2fb69a70ddf1a22ab163f07c957e36e45b12af5fbc08f311a81d506a68907528bfe9da238e84'
                       }
                )),
                self.ws_open_done)

    @tornado.gen.coroutine
    def ws_open_done(self, future):
        if future.exception():
            # TODO: log exception somewhere (console?)
            print('Failed to open Webscoket to Control Center:', future.exception())
        else:
            result=future.result()
            self.ws = result
            
            # TODO subscribe to all that needs subscribed...
            #self.subscribe('agent/3/vlans')
            #self.subscribe('agent/')
            for key in self.synapse.keys('synapse:subscribers:*'):
                path = key.replace('synapse:subscribers:', '')
                self._ws_subscribe(path, force_send=True)
            for path in self.synapse.hgetall('synapse:providers'):
                self._ws_provide(path, force_send=True)
                
            while True:
                try:
                    msg = yield self.ws.read_message()
                except:
                    print('error occured:', traceback.format_exc() )
                    self.ws.close()
                    break
                if msg is None:
                    break # WebSocket closed
                try:
                    self.process_msg(msg)
                except:
                    print('error occured:', traceback.format_exc() )
                    self.ws.close()
        
        # Wait 30 before reopening new connection
        tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=self.RETRY_INTERVAL), self._open_cc_ws )
            
    def process_msg(self, message):
        header, json_data = message.split('\n', 1)
        data = json.loads(json_data)
        command, args = header.split(None, 1)

        if command == 'ANSWER':
            path = args
            # path received, no need to further query it if it was watched
            self.awaited_paths.discard(path)
    
            if data != self.synapse.get(CACHE_PREFIX + path):
                self.synapse.set(CACHE_PREFIX + path, data)
                
                for subscriber in self.synapse.smembers('synapse:subscribers:'+path):
                    self._answer_requester(subscriber, path=path, data=data)


        elif command == 'CALL': # Ignore if no callback was defined
            req_id, path = args.split(None, 1)

            provider = self.synapse.hget('synapse:providers', path)
            if provider:
                self._call_provider(provider, req_id, path, data)

    def _call_provider(self, provider, req_id, path, data):
        self.synapse.lpush( AXON_CALLS.format(name=provider), dict(data=data, req_id=req_id, path=path) )
    
    def run(self):
        tornado.ioloop.IOLoop.instance().start()

import tornado.ioloop, tornado.websocket, tornado.gen, tornado.options
import json, datetime, traceback, time
import tornadoredis
import redis

CACHE_PREFIX = 'cache:'

DENDRITE_COMMANDS = 'synapse:commands'
DENDRITE_ANSWERS = 'synapse:answers'
 
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

def wait_registered():
    wait_for_synapse_ready()
    registered = Axon.is_registered()
    
    while not registered:
        time.sleep(1)
        registered = Axon.is_registered()

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


class Dendrite(object):
    """ Dendrite is the interface to the Central Controller
        
        Subclass this or provide answer_cb and call_cb to constructor.
        
        When subclassing, use add_callback(channel, callback_fn) to listen to other redis queues.
        By default,listens to answer queue and  call queue (that includes the name)
    """
    POST_ANSWER_PATH = '{name}:post:{id}'
    
    #TODO: Once everything runs on python3, replace this by asyncio loop

    def __init__(self, name, answer_cb=None, call_cb=None, timeout_cb=None, timeout=0):
        self.name = name # self name used when communication with synapse.
        self.channel_cb = {}
        self.synapse = Synapse()
        self.timeout = timeout # used to timeout wait on channels

        def add_self_decorator(fn):
            def wrapper(*args, **kwargs):
                return fn(self, *args, **kwargs)
            return wrapper
        
        if answer_cb:
            self.answer_cb = add_self_decorator(answer_cb)
        if call_cb:
            self.call_cb = add_self_decorator(call_cb)
        if timeout_cb:
            self.timeout_cb = add_self_decorator(timeout_cb)

        # add in order, first one higher priority
        self.add_channel(AXON_CALLS.format(name=self.name), self.call_cb)
        self.add_channel(AXON_ANSWERS.format(name=self.name), self.answer_cb)

    def is_registered(self):
        return Axon.is_registered()

    def add_channel(self, channel, cb):
        self.channel_cb[channel] = cb
    
    def answer_cb(self, path, answer):
        # might as well unsubscribe as we do nothing about it...
        self.unsubscribe(path)
    
    def call_cb(self, path, request):
        # might as well unprovide as we do known what to do with it......
        self.unprovide(path)

    def timeout_cb(self):
        pass # to be overridden
    
    def run_for_ever(self):
        while True:
            channel_data_tuple = self.synapse.brpop(self.channel_cb.keys(), self.timeout)
            
            if channel_data_tuple is None: # Timeout
                self.timeout_cb()
            else:
                channel, data = channel_data_tuple
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
                # user added channels    
                else:
                    self.channel_cb[channel](data)
        
    def get_provided_services(self):
        services = set()
        for path, provider in self.synapse.hgetall('synapse:providers').items():
            if provider == self.name:
                services.add(path)
        return services
        
    # REST
        
    def post(self, path, data, wait_connection=True):
        '''
            POST and forget
            if no connection, wait and retry (unless wait_connection is set to False)
        '''
        while True:
            try:
                self.call(path, data)
                break
            except redis.exceptions.ConnectionError:
                if not wait_connection:
                    break
                time.sleep(1)


    def sync_post(self, path, data, timeout=SYNC_CALL_TIMEOUT):
        '''
            Synchronious POST
            Will block until an answer is received
        '''
        post_id = self.synapse.get_unique_id()
        answer_path = self.POST_ANSWER_PATH.format(name=self.name, id=post_id)
        self.call(path, data, answer_path)
        answer_tuple = self.synapse.brpop(answer_path, timeout)
        if answer_tuple and not answer_tuple[1]['error']:
            return answer_tuple[1]['data']
        # TODO: raise exception with error
    
    def sync_register(self, data, timeout=SYNC_CALL_TIMEOUT):
        '''
            Synchronious POST
            Will block until an answer is received
            will return dict 
            { 'error': if there was an error
              'data': data returned by server
              'status': status code
            }
        '''
        post_id = self.synapse.get_unique_id()
        answer_path = self.POST_ANSWER_PATH.format(name=self.name, id=post_id)
        self.register(data, answer_path)
        answer_tuple = self.synapse.brpop(answer_path, timeout)
        if answer_tuple:
            return answer_tuple[1]
        else:
            return {'error': True, 'data': {'__all__': ['Request timed out']}}
    
    def _send_command(self, **data):
        if 'answer_path' not in data:
            data['answer_path'] = AXON_ANSWERS.format(name=self.name)
        self.synapse.lpush(DENDRITE_COMMANDS, data)

    def _send_answer(self, **data):
        self.synapse.lpush(DENDRITE_ANSWERS, data)

        
    def retrieve(self, path):
        self._send_command(cmd='RETRIEVE', path=path)

    def subscribe(self, path):
        self._send_command(cmd='SUBSCRIBE', path=path)

    def unsubscribe(self, path):
        self._send_command(cmd='SUBSCRIBE', path=path)

    def provide(self, path):
        self._send_command(cmd='PROVIDE', path=path, answer_path=AXON_CALLS.format(name=self.name))

    def unprovide(self, path):
        self._send_command(cmd='UNPROVIDE', path=path)

    def call(self, path, data, answer_path=None):
        ''' 
            POST data to path
            if answer_path is None, No answer will be sent  back to requester, but will retry to send it on failure
        '''
        self._send_command(cmd='CALL', path=path, data=data, answer_path=answer_path)

    def register(self, data, answer_path=None):
        self._send_command(cmd='REGISTER', data=data, answer_path=answer_path)

    def answer(self, req_id, answer):
        self._send_answer(req_id=req_id, answer=answer)
        
        
        
        
        
        
        
        
        
        
def check_awaited_path(fn):
    def wrapper(axon, path, *args, **kwargs):
        fn(axon, path, *args, **kwargs)
        
        def check_answered():
            if path in axon.awaited_paths:
                # Reply to requesters from cache if possible:
                retrievers = axon.synapse.smembers('synapse:retrievers:'+path)
                if retrievers and axon.synapse.exists(CACHE_PREFIX + path):
                    for answer_path in retrievers:
                        axon._answer_requester( answer_path, 
                                                data=axon.synapse.get(CACHE_PREFIX + path), 
                                                path=path )
                        axon.synapse.srem('synapse:retrievers:'+path, answer_path)
                    
                # force Resend request
                kwargs['force_send'] = True
                wrapper(axon, path, *args, **kwargs)
        
        # arm timeout
        tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=axon.RETRY_INTERVAL), check_answered)
        
    return wrapper


class Axon:
    RETRY_INTERVAL = 30 #seconds
    CONNECTED_PATH = 'agent:connected'
    AGENT_ID_PATH = 'agent:id'
    AGENT_UUID_PATH = 'agent:uuid'
    AGENT_LOCATION_PATH = 'agent:location'
    synapse = Synapse() # for sync operations
    URL = 'ws://127.0.0.1:8000/ws'
    CC_IPv4 = ['87.98.150.15'] # Control center IPs to be used in NGINX conf: indeed, when no resolver available, NGINX fails if we use fqdn
    CC_IPv6 = ['2001:41d0:2:ba47::1:10'] 

    def __init__(self, url=None):
        self.url = url
        if not self.url:
            self.url = self.URL

        self.registered = self.is_registered()

        self.aredis = tornadoredis.Client() # for blocking operations like brpop .... requires json en/decode...
        self.aredis.connect()

        self.awaited_paths = set()
        self.subscriptions = set()

        # open websocket to control center
        self.ws = None
        self._open_cc_ws()
        
        
        # Listen to commands:
        tornado.ioloop.IOLoop.instance().run_sync(self.listen_commands)
        
    @classmethod
    def generate_nginx_conf(cls, reload=False):
        from mako.template import Template
        import subprocess
        
        axon_template = Template(filename="/origin/core/nginx/axon")
        
        with open ("/etc/nginx/sites-available/axon", "w") as axon_file:
            axon_file.write( axon_template.render(
                                      uuid       = cls.agent_uuid(),
                                      cc_ipv4    = cls.CC_IPv4,
                                      cc_ipv6    = cls.CC_IPv6,
                                      registered = cls.is_registered() 
                           ) )

        # Reload Nginx
        if reload:
            subprocess.call('reload nginx', shell=True)

        
    @classmethod
    def is_connected(cls):
        return cls.synapse.get(cls.CONNECTED_PATH)

    @classmethod
    def redis_set_disconnected(cls):
        return cls.synapse.set(cls.CONNECTED_PATH, False)

    @classmethod
    def redis_set_connected(cls):
        return cls.synapse.set(cls.CONNECTED_PATH, True)


    @classmethod
    def is_registered(cls):
        return bool(cls.synapse.get(cls.AGENT_ID_PATH))

    @classmethod
    def agent_location(cls):
        return cls.synapse.get(cls.AGENT_LOCATION_PATH)

    @classmethod
    def agent_uuid(cls):
        return cls.synapse.get(cls.AGENT_UUID_PATH)
    
    @tornado.gen.coroutine
    def listen_commands(self):
        while True:
            data = yield tornado.gen.Task(self.aredis.brpop, [DENDRITE_ANSWERS, DENDRITE_COMMANDS])
            try:
                if DENDRITE_ANSWERS in data:
                    data = json.loads(data[DENDRITE_ANSWERS])
                    self.process_answer(data['req_id'], data['answer'])
                else:
                    data = json.loads(data[DENDRITE_COMMANDS])
                    self.process_command(data)
            except:
                print('error occured:', traceback.format_exc() )
                
    def process_answer(self, req_id, answer):
        self._ws_send('ANSWER {id}\n{answer}'.format(id=req_id, answer=json.dumps(answer)))
            
    def process_command(self, data):
        if data['cmd'] == 'SUBSCRIBE':
            self.synapse.sadd('synapse:subscribers:'+data['path'], data['answer_path'])
            #reply from cache if available!
            if self.synapse.exists(CACHE_PREFIX + data['path']):
                self._answer_requester( data['answer_path'], 
                                        data=self.synapse.get(CACHE_PREFIX + data['path']), 
                                        path=data['path'] )
            self._ws_subscribe(data['path'])
        
        elif data['cmd'] == 'RETRIEVE':
            self.synapse.sadd('synapse:retrievers:'+data['path'], data['answer_path'])
            self._ws_retrieve(data['path'])
        
        elif data['cmd'] == 'PROVIDE':
            self.synapse.hset('synapse:providers', data['path'], data['answer_path'])
            self._ws_provide(data['path'])
        
        elif data['cmd'] == 'UNPROVIDE':
            self.synapse.hdel('synapse:providers', data['path'])
            self._ws_unprovide(data['path'])

        elif data['cmd'] == 'CALL' and self.registered: # Ignore if not registered
            track_id = str(self.synapse.get_unique_id('axon:track_counter')) # Track ID as string, it does not need to be an integer. It is treated as a string in the rest of the program
            if data['answer_path']:
                # TODO: maybe calls (ie sync posts) should be HTTP directly no added value here to go through websocket, except maybe to use cache when no answer or WS down?
                self.synapse.set('axon:answer_paths:' + str(track_id), data['answer_path'], ex=CALL_TIMEOUT) #If answer takes over CALL_TIMEOUT sec, ignore it...
                self._ws_call(data['path'], track_id, data['data'])
            else:
                # it is our responsibility to get and answer
                self.synapse.hset('axon:awaited_post_answers:data', track_id, data['data'])
                self.synapse.hset('axon:awaited_post_answers:path', track_id, data['path'])
                self.synapse.zadd('axon:awaited_post_answers', track_id, track_id) # use sorted set so that track_ids are ordered...
                self._check_post_answered(track_id)
        elif data['cmd'] == 'REGISTER':
            # Register Agent to account identifiend by admin credentials.
            track_id = str(self.synapse.get_unique_id('axon:track_counter')) # Track ID as string, it does not need to be an integer. It is treated as a string in the rest of the program
            if data['answer_path']:
                self.synapse.set('axon:answer_paths:' + str(track_id), data['answer_path'], ex=CALL_TIMEOUT) #If answer takes over CALL_TIMEOUT sec, ignore it...
            self.ws.write_message('REGISTER {id}\n{data}'.format(id=track_id, data=json.dumps(data['data'])))
                
    def _check_post_answered(self, track_id):
        if self.ws:
            # if websocket closed, retrieval will be make on opening of ws....
            if self.synapse.zscore('axon:awaited_post_answers', track_id):
                # TODO: check if some other paths that are included in this one are still awaiting answer... in that case delay send...
                # still waiting for answer...
                self._ws_call(
                          self.synapse.hget('axon:awaited_post_answers:path', track_id), 
                          track_id, 
                          self.synapse.hget('axon:awaited_post_answers:data', track_id)
                )
                
                def check_post_answered():
                    self._check_post_answered(track_id)
                
                tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=self.RETRY_INTERVAL), check_post_answered)
                
    @check_awaited_path
    def _ws_subscribe(self, path, force_send = False):
        if path not in self.subscriptions or force_send:
            self._ws_send('SUBSCRIBE 0 ' + path)
            self.subscriptions.add(path)
            self.awaited_paths.add(path)

    @check_awaited_path
    def _ws_retrieve(self, path, force_send = False):
        if path not in self.awaited_paths or force_send:
            self._ws_send('RETRIEVE 0 ' + path)
            self.awaited_paths.add(path)

    def _ws_provide(self, path, force_send = False):
        self._ws_send('PROVIDE 0 ' + path)

    def _ws_unprovide(self, path, force_send = False):
        self._ws_send('UNPROVIDE 0 ' + path)
       
    def _ws_call(self, path, track_id, data):
        self._ws_send('CALL {id} {path}\n{data}'.format(path=path, id=track_id, data=json.dumps(data)))            
            
    def _ws_send(self, msg):
            if self.registered and self.ws:
                self.ws.write_message(msg)

    def _answer_requester(self, answer_path, **data):
        self.synapse.lpush(answer_path, data)
        
    def _open_cc_ws(self):    
        tornado.ioloop.IOLoop.instance().add_future(tornado.websocket.websocket_connect(self.url), self.ws_open_done)

    @tornado.gen.coroutine
    def ws_open_done(self, future):
        if future.exception():
            # TODO: log exception somewhere (console?)
            print('Failed to open Websocket to Control Center:', future.exception())
            self.redis_set_disconnected()
        else:
            self.ws = future.result()
            self.redis_set_connected()
            
            for key in self.synapse.keys('synapse:subscribers:*'): # register subscriptions
                path = key.replace('synapse:subscribers:', '')
                self._ws_subscribe(path, force_send=True)
            for path in self.synapse.hgetall('synapse:providers'): # register what we provide
                self._ws_provide(path, force_send=True)
            for track_id in self.synapse.zrange('axon:awaited_post_answers', 0, -1): # send waiting posts
                self._check_post_answered(track_id)
                
            while True:
                try:
                    msg = yield self.ws.read_message()
                except:
                    print('error occured:', traceback.format_exc() )
                    self.ws.close()
                    break
                if msg is None:
                    self.redis_set_disconnected()
                    break # WebSocket closed
                try:
                    self.process_msg(msg)
                except:
                    print('error occured:', traceback.format_exc() )
                    self.ws.close()
        
        # Wait 30 before reopening new connection
        tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=self.RETRY_INTERVAL), self._open_cc_ws )
            
    def process_msg(self, message):
        try:
            header, json_data = message.split('\n', 1)
            if json_data:
                try:
                    data = json.loads(json_data)
                except:
                    data = json_data
            else:
                data = ''
            command, args = header.split(None, 1)
            track_id, path = args.split(None, 1)
    
            if command in ('ANSWER', 'ERROR'):
                if track_id == '0':
                    if command == 'ANSWER':
                        # path received, no need to further query it if it was watched
                        self.awaited_paths.discard(path)
                
                        if data != self.synapse.get(CACHE_PREFIX + path):
                            # data modified: update cache and notify subscribers
                            self.synapse.set(CACHE_PREFIX + path, data)
                            
                            for answer_path in self.synapse.smembers('synapse:subscribers:'+path):
                                self._answer_requester(answer_path, path=path, data=data)
        
                        # answer retrievers
                        for answer_path in self.synapse.smembers('synapse:retrievers:'+path):
                            self._answer_requester(answer_path, path=path, data=data)
                            self.synapse.srem('synapse:retrievers:'+path, answer_path)
                        
                else:
                    # remove from awaited POSTS
                    self.synapse.zrem('axon:awaited_post_answers', track_id) 
                    self.synapse.hdel('axon:awaited_post_answers:data', track_id)
                    self.synapse.hdel('axon:awaited_post_answers:path', track_id)
    
                    # find answer path
                    answer_path = self.synapse.get('axon:answer_paths:' + str(track_id))
                    
                    # if this is an answer do REGISTER, that succeeded, intercept it and use it
                    # when not registered, only command sent is REGISTER, so the answer must be an answer to REGISTER
                    if not self.registered and command == 'ANSWER' and path == 'agent/register':
                        self.synapse.set(self.AGENT_ID_PATH, data['id'])
                        self.synapse.set(self.AGENT_UUID_PATH, data['uuid'])
                        self.registered = True
                        self.generate_nginx_conf(reload=True)
                        
                    if answer_path:
                        if command == 'ERROR':
                            self._answer_requester( answer_path, status=path, data=data, error=True )
                        else:
                            self._answer_requester( answer_path, path=path, data=data, error=False )
    
    
            elif command == 'CALL': # Ignore if no callback was defined
                provider_path = self.synapse.hget('synapse:providers', path)
                if provider_path:
                    self._call_provider(provider_path, track_id, path, data)
    
            elif command == 'LOCATION':
                self.synapse.set(self.AGENT_LOCATION_PATH, path)
        except:
            from origin.event import ExceptionEvent
            ExceptionEvent(source='axon').notify()
        
        
    def _call_provider(self, provider_path, req_id, path, data):
        self.synapse.lpush( provider_path, dict(data=data, req_id=req_id, path=path) )
    
    def run(self):
        tornado.ioloop.IOLoop.instance().start()

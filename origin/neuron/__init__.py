import json, datetime, traceback, time
import redis
from .. import utils

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
        # Add interfaces to data
        data['interfaces'] = list(utils.physical_ifaces())
        
        self._send_command(cmd='REGISTER', data=data, answer_path=answer_path)

    def answer(self, req_id, answer):
        self._send_answer(req_id=req_id, answer=answer)



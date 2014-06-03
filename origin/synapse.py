import json
import pycurl
import websocket
import time
import redis
import threading

class Synapse():
    """ synapse.REST is the interface to the Central Controller
        Calls can be synchronious (post(), http_get()) or async (start_post, request_finished, get_result)
        It is also able to queue objects to post in a pool and send then all at once (JSON array) with postPoolAdd and submitPostPoolIfReady
        It is also the interface to local Redis DB that is used as a cache and for storing agent specific configuration that does not need to be sent to control center.
        Redis commands are passed (almost) directly to python-redis...
    """
    MAX_POOL_SIZE = 50
    MAX_SECS_BETWEEN_ADDS = 60
    BASE_PATH = '127.0.0.1:8000'
    REST_PATH = '/api/'
    WEBSOCKET_PATH = '/ws'
    WS_RESPONSE_TIMEOUT = 60.0 # seconds
    PING_INTERVAL = 3500
    
    def __init__(self, path='', rest_path = BASE_PATH + REST_PATH, ws_path = BASE_PATH + WEBSOCKET_PATH):
        # TODO: separate (and delay) init whether using REST or Websocket
        
        # for REST
        self.multi = pycurl.CurlMulti()
        self.ongoing_request = False
        
        self.output = ""
        
        c = pycurl.Curl()
        c.setopt(pycurl.URL, rest_path + path )
        c.setopt(pycurl.HTTPHEADER, [
                "Content-Type: application/json",
                "Expect:", # Disable the 'Expect: 100-continue' default curl behavior with large bodies to post
         ])
        c.setopt(pycurl.WRITEFUNCTION, self.__output)
        self.connection = c 
        
        self.last_post_time = time.time()
        self.post_pool = []
        
        # for Websockets
        self.subscriptions = set()
        self.retrieves = set()
        self.websocket = None
        self.ws_path = ws_path
        self.message_cb = None
        self.close_cb = None
        self.ws_awaited_paths = set()
        self.ws_event_closed = threading.Event() # Event signal when ws is closed
        # for Redis
        self.redis = redis.Redis()
        
        
    # REST
        
    def get_url(self):
        return 'http://' + self.connection.getinfo(pycurl.EFFECTIVE_URL)
        
    def __output(self, data):
        self.output += data
        
    def post(self, data):
        ''' Synchronious POST '''
        self.output = ''

        c = self.connection
        c.setopt(pycurl.POSTFIELDS, json.dumps(data))
        c.perform()

        return ( c.getinfo(pycurl.HTTP_CODE), self.output )
    
    def http_get(self):
        '''Synchronious GET'''
        self.output = ''

        c = self.connection
        c.setopt(pycurl.HTTPGET, 1)
        c.perform()
        
        return ( c.getinfo(pycurl.HTTP_CODE), json.loads(self.output) )
    
    def start_post(self, data):
        ''' Asynchronious POST '''
        self.output = ''
        self.ongoing_request = True

        c = self.connection
        c.setopt(pycurl.POSTFIELDS, json.dumps(data))
        
        m = self.multi
        m.add_handle(c)
        m.perform()
        
    def request_finished(self):
        ''' check if async request is finished
            If no ongoing requests, returns True
        '''
        if self.ongoing_request:
            return self.multi.select(0)
        return True
    
    def get_result(self):
        ''' retrieves the result of an async request. Will block until request finished.'''
        m = self.multi
        #Poll wait for result to be ready (see pycurl code examples: http://pycurl.sourceforge.net/doc/curlmultiobject.html)
        ret, num_handles = m.perform()
        while num_handles:
            ret = m.select(1.0)
            if ret == -1:
                continue # retry on timeout
            ret, num_handles = m.perform()

        c = self.connection
        if self.ongoing_request:
            m.remove_handle(c)
            self.ongoing_request = False
        
        return ( c.getinfo(pycurl.HTTP_CODE), self.output )
    
    def check_last_request(self):
        # Check how last request went on
        http_code, result = self.get_result()
        if http_code != 201 and http_code != 0:
            # Todo: Raise alert back to CC
            print "Error ", http_code, ': ', result

    def postPoolAdd(self, obj):
        '''
        Add object to POST pool
        '''
        self.post_pool.append(obj)

    def submitPostPoolIfReady(self):
        '''
        Submit POST pool asynchronously if ready (last request finished and (pool size over MAX_POOL_SIZE or MAX_SECS_BETWEEN_ADDS elapsed since last post))
        '''
        if len(self.post_pool) >= self.MAX_POOL_SIZE or self.MAX_SECS_BETWEEN_ADDS <= (time.time() - self.last_post_time):
            # check if last request finished
            if self.request_finished():
                self.check_last_request()
                 
                if self.post_pool:
                    self.start_post(self.post_pool)
                    self.last_post_time = time.time()
                    self.post_pool = []


    def flushPostPool(self):
        self.check_last_request()
        if self.post_pool:
            self.start_post(self.post_pool)
            self.check_last_request()
            
    # WEB SOCKET with redis cache.
    # TODO: use redis for pub sub and have 1 daemon taking care of web socket
    def retrieve(self, path):
        # retrieve from cache
        self._cache_reply(path)

        if not self.websocket:
            self.retrieves.add(path)
        elif path not in self.ws_awaited_paths:
            # send request if not already waiting for that path
            self._ws_get(path)
    def subscribe(self, path):
        # retrieve from cache
        self._cache_reply(path)

        if self.websocket and (path not in self.subscriptions or path not in self.ws_awaited_paths):
            # Send request upstream if not already subscribed or no ongoing connection request is waiting
            self._ws_subscribe(path)

        self.subscriptions.add(path)


    def _ws_get(self, path):
        self.websocket.send('GET ' + self.REST_PATH + path)
        self.ws_awaited_paths.add(path)

    def _ws_subscribe(self, path):
        self.websocket.send('SUBSCRIBE ' + self.REST_PATH + path)
        self.ws_awaited_paths.add(path)

    def _cache_reply(self, path):
        if self.message_cb and self.exists('cache:' + path):
            self.message_cb(path, self.get('cache:' + path))
            
    def _ws_on_open(self, ws):
        for path in self.retrieves:
            self._ws_get(path)
        self.retrieves = set()

        for path in self.subscriptions:
            self._ws_subscribe(path)
        
        # start Thread that will regularly query Control Center if no response has yet arrived
        thread = threading.Thread(target=self._check_awaited_paths)
        thread.setDaemon(True)
        thread.start()
        
    def _check_awaited_paths(self):
        while not self.ws_event_closed.wait(self.WS_RESPONSE_TIMEOUT):
            for path in self.ws_awaited_paths:
                if path in self.subscriptions:
                    self._ws_subscribe(path)
                else:
                    self._ws_get(path)

    def _ws_on_close(self, ws):
        self.ws_event_closed.set() # Notify threads websocket has closed...
        self.websocket = None
        if self.close_cb:
            self.close_cb()

    def _ws_on_message(self, ws, message):
        response = json.loads(message)
        path = response['path'].replace(self.REST_PATH, '', 1)
        # path received, no need to further query it if it was watched
        self.ws_awaited_paths.discard(path)

        self.set('cache:' + path, response['object'])
        self.message_cb(path, response['object'])

    def run_forever(self, message_cb = None, close_cb=None):
        """ Run configurator with all callbacks, if called without arguments, will reconnect websocket with same callbacks, and register same subscriptions"""

        if message_cb:
            self.message_cb = message_cb
        if close_cb:
            self.close_cb = close_cb

        self.ws_event_closed.clear() # make sure websocket closed Event is cleared before opening websocket
        
        # retrieve from cache the values.
        for path in self.subscriptions | self.retrieves:
            self._cache_reply(path)

        self.websocket = websocket.WebSocketApp( "ws://{}".format(self.ws_path),
                                                 on_close = self._ws_on_close,
                                                 on_open = self._ws_on_open,
                                                 on_message = self._ws_on_message )
        

        self.websocket.run_forever(ping_interval=self.PING_INTERVAL)
        
    # REDIS: Wrapper for redis connection that ancodes and decodes object using JSON
    
    def get(self, key):
        ''' returns JSON decoded object in key '''
        data = self.redis.get(key)
        if data == None:
            return None
        return json.loads(data)
    def set(self, key, value):
        ''' JSON encodes object and stores it '''
        return self.redis.set( key, json.dumps(value, sort_keys=True) )
    
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
        return { k: json.loads(v) for k, v in self.redis.hgetall(key).items() }

    def hget(self, key, field):
        data = self.redis.hget(key, field)
        if data == None:
            return None
        return json.loads(data)

    def hset(self, key, field, value):
        return self.redis.hset(key, field, json.dumps(value, sort_keys=True))

    # Sets
    def sismember(self, key, value):
        return self.redis.sismember(key, json.dumps(value, sort_keys=True))

    def sadd(self, key, *args):
        self.redis.sadd(key, *(json.dumps(v, sort_keys=True) for v in args))

    def srem(self, key, *args):
        self.redis.srem(key, *(json.dumps(v, sort_keys=True) for v in args))
    
    def pipeline(self):
        return self.redis.pipeline()

    def transaction(self, func, *watches, **kwargs):
        # create a specific pipeline each time...
        return self.redis.transaction(func, *watches, **kwargs)
    
    def exists(self, key):
        return self.redis.exists(key)

    def publish(self, channel, msg):
        return self.redis.publish(channel, json.dumps(msg, sort_keys=True))

    def type(self, key):
        return self.redis.type(key)
    
    def smembers(self, key):
        return set(json.loads(v) for v in self.redis.smembers(key))

    def lmembers(self, key):
        return [json.loads(v) for v in self.redis.lrange(key, 0, -1)]

    def pubsub(self):
        return self.redis.pubsub()

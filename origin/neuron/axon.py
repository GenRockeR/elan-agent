import tornado.ioloop, tornado.websocket, tornado.gen, tornado.options
import tornadoredis
import traceback
import datetime, time
import json
from . import Synapse, CACHE_PREFIX, wait_for_synapse_ready, DENDRITE_ANSWERS, DENDRITE_COMMANDS, CALL_TIMEOUT
from .. import utils


def wait_registered():
    wait_for_synapse_ready()
    registered = Axon.is_registered()
    
    while not registered:
        time.sleep(1)
        registered = Axon.is_registered()




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
        
        self.nowait_on_reopen = False
        
        # Listen to commands:
        tornado.ioloop.IOLoop.instance().run_sync(self.listen_commands)
        
    @classmethod
    def generate_nginx_conf(cls, reload=False):
        from mako.template import Template
        
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
            utils.reload_service('nginx')

        
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
        try:
            return bool(cls.synapse.get(cls.AGENT_ID_PATH))
        except:
            # Be robust when synapse not connected... (during install for example)
            return False

    @classmethod
    def agent_location(cls):
        return cls.synapse.get(cls.AGENT_LOCATION_PATH)

    @classmethod
    def agent_uuid(cls):
        try:
            return cls.synapse.get(cls.AGENT_UUID_PATH)
        except:
            # Be robust when synapse not connected... (during install for example)
            return
    
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
        if self.nowait_on_reopen:
            wait_for = 1
            self.nowait_on_reopen = False
        else:
            wait_for = self.RETRY_INTERVAL
        tornado.ioloop.IOLoop.instance().add_timeout( datetime.timedelta(seconds=wait_for), self._open_cc_ws )
            
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
                        # close socket so we start a new one a do correct initialization...
                        self.nowait_on_reopen = True
                        self.ws.close()
                        
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
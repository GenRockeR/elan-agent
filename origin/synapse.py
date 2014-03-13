import json
import pycurl
import time

class Synapse():
    """ Synapse is the interface to the Central Controller
        Calls can be synchronious (post()) or async (start_post, request_finished, get_result)
    """
    MAX_POOL_SIZE = 50
    MAX_SECS_BETWEEN_ADDS = 60
    BASE_PATH = "127.0.0.1:8000/api/"
    
    def __init__(self, path='', base_path = BASE_PATH):
        self.multi = pycurl.CurlMulti()
        self.ongoing_request = False
        
        self.output = ""
        
        c = pycurl.Curl()
        c.setopt(pycurl.URL, base_path + path )
        c.setopt(pycurl.HTTPHEADER, [
                "Content-Type: application/json",
                "Expect:", # Disable the 'Expect: 100-continue' default curl behavior with large bodies to post
         ])
        c.setopt(pycurl.WRITEFUNCTION, self.__output)
        self.connection = c 
        
        self.last_post_time = time.time()
        self.post_pool = []

        
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

        

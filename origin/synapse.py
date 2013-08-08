import json
import pycurl

class Synapse():
    """ Synapse is the interface to the Central Controller
        Calls can be synchronious (post()) or async (start_post, request_finished, get_result)
    """
    def __init__(self, path=''):
        self.multi = pycurl.CurlMulti()
        self.ongoing_request = False
        
        self.output = ""
        
        c = pycurl.Curl()
        c.setopt(pycurl.URL, "127.0.0.1:8000/" + path + '/')
        c.setopt(pycurl.HTTPHEADER, [
                # TODO: Remove that token from somewhere as it will get added by synapse module
                "Authorization: Token 74d6623e97f758efcc3832cae0880bf3f4240d22f1818767fe7f2fb69a70ddf1a22ab163f07c957e36e45b12af5fbc08f311a81d506a68907528bfe9da238e84",
                "Content-Type: application/json",
                "Expect:", # Disable the 'Expect: 100-continue' default curl behavior with large bodies to post
         ])
        c.setopt(pycurl.WRITEFUNCTION, self.__output)
        c.setopt(pycurl.POST, 1)
        self.connection = c 
        
    def __output(self, data):
        self.output += data
        
    def post(self, data):
        ''' Synchronious POST '''
        self.output = ''

        c = self.connection
        c.setopt(pycurl.POSTFIELDS, json.dumps(data))
        c.perform()

        return ( c.getinfo(pycurl.HTTP_CODE), self.output )
    
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

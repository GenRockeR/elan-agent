from origin.neuron import Dendrite, Synapse
from origin.event import Event
from origin import nac, session
import datetime, re

CONF_PATH = 'conf:captive-portal'
GUEST_ACCESS_CONF_PATH = 'conf:guest-access'
PENDING_GUEST_REQUESTS_PATH = 'captive-portal:guest-request:pending'

EDGE_AGENT_FQDN = 'edge-agent.origin-nexus.com'
# TODO: get these from FQDN
EDGE_AGENT_FQDN_IP = '8.8.8.8'
EDGE_AGENT_FQDN_IP6 = '2001:41d0:2:ba47::1000:1000'

CAPTIVE_PORTAL_FQDN = 'captive-portal.origin-nexus.com'
CAPTIVE_PORTAL_FQDN_IP = '8.8.8.9'
CAPTIVE_PORTAL_FQDN_IP6 = '2001:41d0:2:ba47::1000:1010'


def submit_guest_request(request):
    ''' submits sponsored guest access request and return ID of request'''
    d = GuestAccessManager()
    r = d.sync_post('guest-request', request)
    if r:
        request_id = r['id']
        
        d.synapse.sadd(PENDING_GUEST_REQUESTS_PATH,request['mac'])
        
        return request_id

def is_authz_pending(mac):
    return Synapse().sismember(PENDING_GUEST_REQUESTS_PATH, mac)

class Administrator:
    ADMINISTRATOR_CONF_PATH = 'conf:administrator'
    synapse = Synapse()
    @classmethod
    def get(cls, login):
        params = cls.synapse.hget(cls.ADMINISTRATOR_CONF_PATH, login)
        if not params:
            return None
        return cls(login=login, **params)
    
    @classmethod
    def add(cls, **kwargs):
        if 'email' in kwargs and 'password' in kwargs:
            login = kwargs.pop('email')
            cls.synapse.hset(cls.ADMINISTRATOR_CONF_PATH, login, kwargs)
            return True
        return False

    @classmethod
    def delete_all(cls):
        cls.synapse.delete(cls.ADMINISTRATOR_CONF_PATH)


    def __init__(self, login, password, **kwargs):
        self.login = login
        self.password = password
        for key in kwargs:
            setattr(self, key, kwargs[key])
        
    def check_password(self, password):
        from django.contrib.auth.hashers import check_password
        return check_password(password, self.password)
        
class GuestAccessManager(Dendrite):
    MAC_AUTHS_PATH = 'guest-access:auth:mac'
    def __init__(self):
        super().__init__('guest-access-manager')
        self.subscribe('guest-authorization/active')
    
    def answer_cb(self, path, authorizations):
        if path == 'guest-authorization/active':
            # Here we get only valid authz/authentications
            authz_by_mac = {}
            for authz in authorizations:
                # check authz has not expired: we do not receive updates on expiration, this means on restart of the service we receive a cached response with potentially expired authz.
                till = datetime.datetime.strptime(authz['till'][0:19], '%Y-%m-%dT%H:%M:%S')
                if till > datetime.datetime.utcnow(): # dates sent back are UTC
                    mac = authz['mac']
                    if mac not in authz_by_mac:
                        authz_by_mac[mac] = []
                    authz_by_mac[mac].append(authz)
            
            current_mac_with_authz = self.synapse.smembers(self.MAC_AUTHS_PATH)
    
            for mac in current_mac_with_authz - set(authz_by_mac.keys()):
                session.remove_authentication_sessions_by_source(mac, 'guest')
                nac.checkAuthz(mac, 'guest', end_reason='revoked') # TODO: add revoker info + comment
                self.synapse.srem(self.MAC_AUTHS_PATH, mac)
    
            for mac in set(authz_by_mac.keys()):
                # Authz not pending any more
                self.synapse.srem(PENDING_GUEST_REQUESTS_PATH, mac)
                
                self.synapse.sadd(self.MAC_AUTHS_PATH, mac)
                session.remove_authentication_sessions_by_source(mac, 'guest')
                for authz in authz_by_mac[mac]:
                    till_str = authz['till'][0:19] # get rid of milliseconds if present
                    
                    till = (datetime.datetime.strptime(till_str, '%Y-%m-%dT%H:%M:%S') - datetime.datetime(1970, 1, 1)).total_seconds()
                    session.add_authentication_session(mac, source='guest', till=till, login=authz['sponsor_login'], authentication_provider=authz['sponsor_authentication_provider'], guest_authorization=authz['id'])
                nac.checkAuthz(mac)
            
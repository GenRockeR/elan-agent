from origin.neuron import Synapse, Dendrite
import subprocess, datetime, re
from origin import session

DISCONNECT_NOTIFICATION_PATH = 'device:vlan_mac_disconnected' # TODO Factorize: also in session_trackerd

AUTHORIZATION_CHANGE_CHANNEL = 'nac:authz:change' " notify that authz changed for mac"

AUTHZ_MAC_EXPIRY_PATH = 'nac:authz:expiry' # sorted set with expiry as score, mac will be used as key of session (we only keep current sessions)
AUTHZ_SESSIONS_BY_MAC_PATH = 'nac:authz:sessions' # hash
AUTHZ_SESSIONS_SEQUENCE_PATH = 'nac:authz:sequence'

dendrite = Dendrite('nac')
synapse = dendrite.synapse

# Redis authorizations objects are set straight away, but opening of fw is async. (done by mac authz daemon)
# mac authz daemon is also responsible for de authorizing mac on expiry
 
def newAuthz(mac, source, no_duplicate_source=False, **auth):
    '''gets new Authorization by adding new authentication. if no_duplicate_source is true, it will first remove any auth from that source first
    Mainly a shortcut for session.add_authentication and nac.checkAuthz 
    '''
    
    # TODO: in redis session -> use a key to lock ?
    if no_duplicate_source:
        session.remove_authentication_sessions_by_source(mac, source)

    session.add_authentication_session(mac, source=source, **auth)
    
    return checkAuthz(mac)


def checkAuthz(mac, remove_source=None, end_reason='overridden', **kwargs):
    '''
    Asks CC what Authorization should be granted to the mac, based on current authentications
    First, an authentication source can be removed using remove_source
    '''
    if remove_source is not None:
        session.remove_authentication_sessions_by_source(mac, remove_source)
    
    assignments = get_network_assignments(mac)

    old_authz = RedisMacAuthorization.getByMac(mac)
    
    if assignments:
        authz = RedisMacAuthorization( mac = mac, **assignments )
        
        if authz != old_authz:
            if old_authz:
                RedisMacAuthorization.deleteByMac(mac)
                notify_end_authorization_session(old_authz, reason=end_reason, **kwargs)
            authz.save()
            authzChanged(mac)
            notify_new_authorization_session(authz)
        
        return authz
    else:
        if old_authz:
            RedisMacAuthorization.deleteByMac(mac)
            authzChanged(mac)
            notify_end_authorization_session(old_authz, reason='expired')

def getAuthz(mac):
    ''' Returns current authz, and if none, checks if there should be one... '''
    authz = RedisMacAuthorization.getByMac(mac)
    if authz:
        return authz
    return checkAuthz(mac)
    
def authzChanged(mac):
    '''
    notify Mac Authz Manager that authz for mac has changed. Should not need to call this directly
    '''
    synapse.lpush(AUTHORIZATION_CHANGE_CHANNEL, mac)


def macDisconnected(mac, time=None):
    if time is None:
        time = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() #Epoch

    synapse.lpush(DISCONNECT_NOTIFICATION_PATH, dict(mac=mac, time=time))



def get_network_assignments(mac, port=None, current_auth_sessions=None):
    if current_auth_sessions is None:
        current_auth_sessions = session.get_authentication_sessions(mac)
    if port is None:
        port = synapse.hget(session.MAC_PORT_PATH, mac)
        
    return dendrite.sync_post('agent/self/assignments', {'auth_sessions': current_auth_sessions, 'mac': mac, 'port': port})

def tzaware_datetime_to_epoch(dt):
    return (dt - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()


def notify_new_authorization_session(authz, start=None):
    '''
        start and end are Epoch
    '''
    data = authz.__dict__.copy()
    
    # CC expects vlan_id, not vlan
    data['vlan_id'] = authz.vlan
    del data['vlan']
    
    # CC expects authorized, not bridge
    data['authorized'] = authz.bridge
    del data['bridge']
    
    if data.get('till', None): # format date
        data['till'] = session.format_date(data['till'])
        
    dendrite.post('mac/{mac}/authorization'.format(mac=authz.mac), dict(start=session.format_date(start), **data))

def notify_end_authorization_session(authz, reason, end=None, **kwargs):
    ''' start is Epoch '''

    kwargs['termination_reason'] = reason
    kwargs['end'] = session.format_date(end)

    dendrite.post('mac/{mac}/authorization/local_id:{local_id}/end'.format(mac=authz.mac, local_id=authz.local_id), kwargs)


def macAllowed(mac, vlan):
    authz = RedisMacAuthorization.getByMac(mac)
    return authz is not None and str(authz.vlan) == str(vlan) 

class RedisMacAuthorization(object):
    def __init__(self, mac, vlan, bridge, till_disconnect, till=None, local_id=None, **kwargs):
        self.local_id = local_id # local_id is mainly used for sync with CC. we find current sessions by mac
        self.mac = mac
        self.vlan = vlan
        self.bridge = bridge
        self.till_disconnect = till_disconnect
        self.till = till
        
        for key in kwargs:
            setattr(self, key, kwargs[key])
    
    def __eq__(self, other):
        ''' Equality if all params match excluding mac and local_id. mac because we may want to compare authz of 2 macs'''
        if not isinstance(other, RedisMacAuthorization) or self.__dict__.keys() != other.__dict__.keys():
            return False 
        for key in self.__dict__:
            if key in ('mac', 'local_id'):
                continue
            if getattr(self, key) != getattr(other, key):
                return False
        return True
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def save(self):
        if self.local_id is None:
            self.local_id = synapse.get_unique_id(AUTHZ_SESSIONS_SEQUENCE_PATH)
            
        if self.till is None:
            till = float('+inf')
        else:
            till = self.till

        pipe = synapse.pipe
        pipe.zadd(AUTHZ_MAC_EXPIRY_PATH, till, self.mac )
        pipe.hset(AUTHZ_SESSIONS_BY_MAC_PATH, self.mac, self.__dict__)
        pipe.execute()
    
    @classmethod
    def deleteByMac(cls, mac):
        pipe = synapse.pipe
        pipe.hget(AUTHZ_SESSIONS_BY_MAC_PATH, mac)
        pipe.zrem(AUTHZ_MAC_EXPIRY_PATH, mac)
        pipe.hdel(AUTHZ_SESSIONS_BY_MAC_PATH, mac)
        result = pipe.execute()
        authz_session = result[0]

        if authz_session is not None:
            return cls(**authz_session)
    
    @classmethod
    def getByMac(cls, mac):
        auth_session = synapse.hget(AUTHZ_SESSIONS_BY_MAC_PATH, mac)
        
        if auth_session is not None:
            return cls(**auth_session)
    
class MacAuthorizationManager(Dendrite):
    def __init__(self):
        super().__init__(self, 'mac-authorizations')

        self.fw_mac_allowed_vlans = {}
        
        self.add_channel(AUTHORIZATION_CHANGE_CHANNEL, self.handle_authz_changed)
        self.add_channel(DISCONNECT_NOTIFICATION_PATH, self.handle_disconnection)

        self.check_expired_authz()

        self.init_macs()
        
    def init_macs(self):
        # on startup, initialize sets
        # TODO: this should get vlans from network conf to flush nft sets and it should use fw_allow mac for each. Even if it is not in a transaction and not very efficient, it is OK as this should not restart often  
        cmd = ''
        vlans = set()
        for mac in self.synapse.zmembers(AUTHZ_MAC_EXPIRY_PATH):
            authz = RedisMacAuthorization.getByMac(mac)
            vlans.add(authz.vlan)
            if authz.bridge:
                self._fw_cache_add(mac, authz.vlan)
                cmd += 'nft add element bridge origin a_v_{vlan} {{{mac}}};'.format(vlan=authz.vlan, mac=mac)
        for vlan in vlans:
            cmd = "nft add set bridge origin a_v_{vlan} '{{type ether_addr;}}';nft flush set bridge origin a_v_{vlan};".format(vlan=vlan) + cmd
             
        subprocess.call(cmd, shell=True)

    def removeAuthz(self, mac, reason, authz=None):
        if authz is None:
            authz = RedisMacAuthorization.getByMac(mac)
        if authz:
            RedisMacAuthorization.deleteByMac(mac)
            notify_end_authorization_session(authz, reason=reason)
        self.fw_disallow_mac(mac)
        
        return authz
    
    def fw_allowed_vlans(self, mac):
        return self.fw_mac_allowed_vlans.get(mac, set())
    
    def _fw_cache_del(self, mac, vlan):
        vlans = self.fw_mac_allowed_vlans.get(mac, None)
        if vlans:
            vlans.remove(vlan)
            if not vlans:
                del self.fw_mac_allowed_vlans[mac]

    def _fw_cache_add(self, mac, vlan):
        vlans = self.fw_mac_allowed_vlans.get(mac, None)
        if vlans:
            vlans.add(vlan)
        else:
            self.fw_mac_allowed_vlans[mac] = {vlan}
            
        
    def fw_allow_mac(self, mac, *vlans):
        "Opens access on the vlan ids specified an closes all the others, if any"
        vlans = set(vlans)
        cmd = ''
        for vlan in self.fw_allowed_vlans(mac) - vlans:
            self._fw_cache_del(mac, vlan)
            cmd += 'nft delete element bridge origin a_v_{vlan} {{{mac}}};'.format(vlan=vlan, mac=mac) 
        for vlan in vlans - self.fw_allowed_vlans(mac):
            self._fw_cache_add(mac, vlan)
            cmd += 'nft add element bridge origin a_v_{vlan} {{{mac}}};'.format(vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)
        

    def fw_disallow_mac(self, mac):
        ''' 
        Disallows MAC
        '''
        self.fw_allow_mac(mac)  # on no vlans
        #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)
            
    def authzChanged(self, mac):
        authz = RedisMacAuthorization.getByMac(mac)
        if authz and authz.bridge:
            self.fw_allow_mac(mac, authz.vlan)
        else:
            self.fw_disallow_mac(mac)
        
    def handle_authz_changed(self, mac):
        self.authzChanged(mac)
        # Check if authz have expired and set correct timeout 
        self.check_expired_authz()

    def handle_disconnection(self, data):
        authz = RedisMacAuthorization.getByMac(data['mac'])
        if authz and authz.till_disconnect:
            self.removeAuthz(data['mac'], reason='disconnected', authz=authz)
            self.authzChanged(data['mac'])
        session.end(data['mac'], time=data['time'])
        
        
        # Check if authz have expired and set correct timeout 
        self.check_expired_authz()

    
    def timeout_cb(self):
        self.check_expired_authz()
        
    def check_expired_authz(self):
        now = tzaware_datetime_to_epoch(datetime.datetime.now(datetime.timezone.utc))
        for mac in self.synapse.zrangebyscore(AUTHZ_MAC_EXPIRY_PATH, float('-inf'), now):
            self.removeAuthz(mac, reason='expired')
            # check new authz in other thread to not block.
            import threading
            thread = threading.Thread(target=checkAuthz, args=(mac,))
            thread.start()
        
        # get next mac to expire
        next_expiry_date = float('inf')
        for mac, epoch_expire in self.synapse.zrange(AUTHZ_MAC_EXPIRY_PATH, 0, 0, withscores=True): # returns first mac to expire
            if next_expiry_date > epoch_expire:
                next_expiry_date = epoch_expire
            
        # set timeout for next check
        if next_expiry_date == float('inf'):
            self.timeout = 0
        else:
            self.timeout = int(next_expiry_date - now) + 1
    
        
    
    

from origin.neuron import Synapse, Dendrite
import subprocess, datetime, re
from origin import session
import threading

DISCONNECT_NOTIFICATION_PATH = 'device:vlan_mac_disconnected' # TODO Factorize: also in session_trackerd

AUTHORIZATION_CHANGE_CHANNEL = 'nac:authz:change' " notify that authz changed for mac"

AUTHZ_MAC_EXPIRY_PATH = 'nac:authz:expiry' # sorted set with expiry as score, mac will be used as key of session (we only keep current sessions)
AUTHZ_SESSIONS_BY_MAC_PATH = 'nac:authz:sessions' # hash
AUTHZ_SESSIONS_SEQUENCE_PATH = 'nac:authz:sequence'


CHECK_AUTHZ_PATH = 'mac/check-authz'


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
        return None

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
    # TODO: when CC unreachable or Error, retry in a few seconds (maybe use mac authz manager daemon for that) 

def tzaware_datetime_to_epoch(dt):
    return (dt - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()


def notify_new_authorization_session(authz, start=None):
    '''
        start and end are Epoch
    '''
    data = authz.__dict__.copy()
    
    if data.get('till', None): # format date
        data['till'] = session.format_date(data['till'])
        
    dendrite.post('mac/{mac}/authorization'.format(mac=authz.mac), dict(start=session.format_date(start), **data))

def notify_end_authorization_session(authz, reason, end=None, **kwargs):
    ''' start is Epoch '''

    kwargs['termination_reason'] = reason
    kwargs['end'] = session.format_date(end)

    dendrite.post('mac/{mac}/authorization/local_id:{local_id}/end'.format(mac=authz.mac, local_id=authz.local_id), kwargs)


class RedisMacAuthorization(object):
    def __init__(self, mac, assign_vlan, allow_on, bridge_to, till_disconnect, till=None, local_id=None, **kwargs):
        self.local_id = local_id # local_id is mainly used for sync with CC. we find current sessions by mac
        self.mac = mac
        self.assign_vlan = assign_vlan
        self.allow_on = set(allow_on)
        self.bridge_to = set(bridge_to)
        self.till_disconnect = till_disconnect
        self.till = till
        
        for key in kwargs:
            setattr(self, key, kwargs[key])
    
    def __eq__(self, other):
        ''' Equality if all params match excluding mac and local_id. mac because we may want to compare authz of 2 macs'''
        if not isinstance(other, RedisMacAuthorization) or self.__dict__.keys() != other.__dict__.keys():
            return False
        
        for key in self.__dict__.keys() - {'mac', 'local_id'}:
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
    ''' Class to manage FW authz of Macs
        It also provides a service to check Authz of Macs when something has changed (Tags, ...)
    '''
    def __init__(self):
        super().__init__(self, 'mac-authorizations')

        self.fw_mac_allowed_vlans = {}
        self.fw_mac_bridged_vlans = {}
        
        self.add_channel(AUTHORIZATION_CHANGE_CHANNEL, self.handle_authz_changed)
        self.add_channel(DISCONNECT_NOTIFICATION_PATH, self.handle_disconnection)
        
        self.provide(CHECK_AUTHZ_PATH)

        self.check_expired_authz()

        self.init_macs()
        
    def init_macs(self):
        # on startup, initialize sets
        # TODO: this should get vlans from network conf to flush nft sets and it should use fw_allow mac for each. Even if it is not in a transaction and not very efficient, it is OK as this should not restart often (TODO when flush sets works...) 
        for mac in self.synapse.zmembers(AUTHZ_MAC_EXPIRY_PATH):
            authz = RedisMacAuthorization.getByMac(mac)
            self.fw_allow_mac(mac, on=authz.allow_on, to=authz.bridge_to)

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
    
    def _fw_cache_allow_on_del(self, mac, vlan):
        vlans = self.fw_mac_allowed_vlans.get(mac, None)
        if vlans:
            vlans.remove(vlan)
            if not vlans:
                del self.fw_mac_allowed_vlans[mac]

    def _fw_cache_allow_on_add(self, mac, vlan):
        vlans = self.fw_mac_allowed_vlans.get(mac, None)
        if vlans:
            vlans.add(vlan)
        else:
            self.fw_mac_allowed_vlans[mac] = {vlan}
            
    def fw_bridged_vlans(self, mac):
        return self.fw_mac_bridged_vlans.get(mac, set())
    
    def _fw_cache_bridge_to_del(self, mac, vlan):
        vlans = self.fw_mac_bridged_vlans.get(mac, None)
        if vlans:
            vlans.remove(vlan)
            if not vlans:
                del self.fw_mac_bridged_vlans[mac]

    def _fw_cache_bridge_to_add(self, mac, vlan):
        vlans = self.fw_mac_bridged_vlans.get(mac, None)
        if vlans:
            vlans.add(vlan)
        else:
            self.fw_mac_bridged_vlans[mac] = {vlan}
            
        
    def fw_allow_mac(self, mac, on=None, to=None):
        "Opens access on the vlan ids specified an closes all the others, if any"
        if on is None:
            on = set()
        if to is None:
            to = set()
        
        # TODO: use nft from pyroute2 when ready
        with subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True, stdout=subprocess.DEVNULL) as nft_process:
            def nft(*cmds):
                print(*cmds, file=nft_process)
            
            for vlan in self.fw_allowed_vlans(mac) - on:
                self._fw_cache_allow_on_del(mac, vlan)
                nft('delete element bridge origin mac_allowed_on_vlan {{ {mac} . {vlan} }};'.format(vlan=vlan, mac=mac))
            for vlan in on - self.fw_allowed_vlans(mac):
                self._fw_cache_allow_on_add(mac, vlan)
                nft('add element bridge origin mac_allowed_on_vlan {{ {mac} . {vlan} }};'.format(vlan=vlan, mac=mac)) 

            for vlan in self.fw_bridged_vlans(mac) - to:
                self._fw_cache_bridge_to_del(mac, vlan)
                nft('delete element bridge origin mac_access_to_vlan {{ {mac} . {vlan} }};'.format(vlan=vlan, mac=mac))
            for vlan in on - self.fw_allowed_on(mac):
                self._fw_cache_bridge_to_add(mac, vlan)
                nft('add element bridge origin mac_access_to_vlan {{ {mac} . {vlan} }};'.format(vlan=vlan, mac=mac)) 

    def fw_disallow_mac(self, mac):
        ''' 
        Disallows MAC
        '''
        self.fw_allow_mac(mac)  # on no vlans
        #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)
            
    def authzChanged(self, mac):
        authz = RedisMacAuthorization.getByMac(mac)
        self.fw_allow_mac(mac, on=authz.allow_on, to=authz.bridge_to)
    
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
    
    def call_cb(self, path, data):
        if path == CHECK_AUTHZ_PATH:
            for mac in data['macs']:
                if session.is_online(mac):
                    thread = threading.Thread(target=checkAuthz, args=(mac,))
                    thread.start()
    
    

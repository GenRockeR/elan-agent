from origin.neuron import Synapse, Dendrite
import subprocess, datetime, re
from origin import session

DISCONNECT_NOTIFICATION_PATH = 'device:vlan_mac_disconnected' # TODO Factorize: also in session_trackerd
SESSION_END_NOTIFICATION_PATH = 'device:session_end_notification' # same

VLAN_AUTH_SESSION_PATH = 'vlan:authz'

ALLOWED_MACS_PATH_PATTERN = 'vlan:{vlan}:allowed_macs' # sorted set with epoch expiry time (or inf) as score. ALL authorized macs are in there, even thos that expire on disconnect
DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN = 'vlan:{vlan}:disallowed_macs_on_disconnect' # set

AUTHORIZATION_CHANNEL = 'vlan_mac_authorizations'

synapse = Synapse()

def tzaware_datetime_to_epoch(dt):
    return (dt - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()

def macAllowed(mac, vlan):
    return bool( Synapse().zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac) )
    # note: no need to check expiry as macs are removed when expired...

def macAuthz(mac, vlan):
    '''
        returns tuple of (datetime: until which mac is authorized, boolean: MAC should be disallowed on disconnect) 
    '''
    return datetime.datetime.fromtimestamp(synapse.zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)),  synapse.ismember(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

def allowMAC(mac, vlan, till_date=None, till_disconnect=False):
    '''
        Allow Mac on VLAN.
        if both, till_date and till_disconnect, first one that occurs disallow mac.
        till_date MUST be a timezone AWARE datetime
    '''
    params = { 'mac' : mac, 'vlan': vlan, 'action': 'allow', 'till_disconnect': till_disconnect }
    if till_date:
        params['till_date'] = tzaware_datetime_to_epoch(till_date) # Pass as EPOCH
    Synapse().lpush(AUTHORIZATION_CHANNEL, params)
    
def disallowMAC(mac, vlan, reason):
    Synapse().lpush(AUTHORIZATION_CHANNEL, { 'mac' : mac, 'vlan': vlan, 'action': 'disallow', 'reason': reason } )

    

class MacAuthorizationManager(Dendrite):
    def __init__(self):
        super().__init__(self, 'firewall')
        
        self.add_channel(AUTHORIZATION_CHANNEL, self.handle_request)
        self.add_channel(DISCONNECT_NOTIFICATION_PATH, self.handle_disconnection)

        # get VLANS that are managed by controller.
        self.vlans = set(re.search(ALLOWED_MACS_PATH_PATTERN.format(vlan='(?P<vlan>.+)'), key).group('vlan') for key in self.synapse.keys( ALLOWED_MACS_PATH_PATTERN.format(vlan='*') ))

        self.check_expired_authz()

        self.init_macs()
        
    def init_macs(self):
        # on startup, initialize sets
        # TODO: this should be done in a transaction but 'nft flush set ...' does not work... 
        cmd = ''
        for vlan in self.vlans:
            for family in ['bridge', 'ip', 'ip6']:
                cmd += 'nft flush set {family} origin a_v_{vlan};'.format(family=family, vlan=vlan)
                for mac in self.synapse.zmembers(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan)):
                    cmd += 'nft add element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)

    def end_till_disconnect_sessions(self, mac, source=None):
        authz = self.synapse.hget('VLAN_AUTH_SESSION_PATH', mac) # list of authz
        new_authz = []
        for a in authz:
            if a['bridge'] and a['till_disconnect']:
                disallowMAC(mac, a['vlan'], reason=source)
                session.notify_end_authorization_session(mac, a['vlan'])
            else:
                new_authz.append(a)
    
        self.synapse.hset('VLAN_AUTH_SESSION_PATH', mac, authz)
        return authz
    
        
    def set_authorization(self, mac, source, port=None, auth_provider=None, till_disconnect=None, till=None, **kwargs):
        '''
            will create new authz or use existing one and return it...
            One 1 authz with till_disconnect can be active. if authz is different, will end that authorization. 
            Authorization will return VLAN assigned and if whether or not to bridge MAC
             
        '''
        if till_disconnect:
            current_authz = self.end_till_disconnect_sessions(mac, source=source)
        else:
            current_authz = self.synapse.hget('VLAN_AUTH_SESSION_PATH', mac) # list of authz
            
        authz = self.check_authz_rules({
            'request': dict(
                            mac=mac,
                            source=source,
                            port=port,
                            **kwargs
            ),
            'current': current_authz  
        })
        
        if authz not in current_authz:
            current_authz.append(authz)
            self.synapse.hset('VLAN_AUTH_SESSION_PATH', mac, authz)
        
        return authz
        

    def allow_mac(self, mac, vlan, till_date, till_disconnect):
        ''' Allows mac on VLAN for period and/or till disconnection. *NO* notification is sent to CC: it is the responsibility of the authorizer'''
        self.vlans.add(vlan)
        self.synapse.zadd(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), till_date, mac)
        if till_disconnect:
            self.synapse.sadd(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)
        else:
            # new authorization so we remove previous authz, if any
            self.synapse.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

        cmd = ''
        for family in ['bridge', 'ip', 'ip6']:
            cmd += 'nft add element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)
        

    def disallow_mac(self, mac, vlan, reason='expired'):
        ''' Disallows MAC on VLAN and ends session on CC  (unless reason is revoked, because revocations are made on CC)'''

        self.synapse.zrem(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)
        self.synapse.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

        cmd= ''
        for family in ['bridge', 'ip', 'ip6']:
            cmd += 'nft delete element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)
        #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)
        
        # end session
        if reason != 'revoked':
            session.notify_end_authorization_session(mac, vlan, termination_reason=reason)
            
    def handle_request(self, item):
        if item['action'] == 'allow':
            till_date = item.get('till_date', float('inf'))
            self.allow_mac(mac=item['mac'], vlan=item['vlan'], till_date=till_date, till_disconnect=item['till_disconnect'])

        else:
            self.disallow_mac(mac=item['mac'], vlan=item['vlan'], reason=item['reason'])
        
        # Check if authz have expired and set correct timeout 
        self.check_expired_authz()

    def handle_disconnection(self, item):
        if self.synapse.sismember( DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=item['vlan']), item['mac'] ):
            self.disallow_mac(mac=item['mac'], vlan=item['vlan'], reason='disconnected')
        
        # Check if authz have expired and set correct timeout 
        self.check_expired_authz()

    
    def timeout_cb(self):
        self.check_expired_authz()
        
    def check_expired_authz(self):
        now = tzaware_datetime_to_epoch(datetime.datetime.now(datetime.timezone.utc))
        next_expiry_date = float('inf')
        for vlan in self.vlans:
            key = ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan)
            for mac in self.synapse.zrangebyscore(key, float('-inf'), now):
                self.disallow_mac(mac, vlan, reason='expired')
            
            # get next mac to expire
            for mac, epoch_expire in self.synapse.zrange(key, 0, 0, withscores=True): # returns first mac to expire
                if next_expiry_date > epoch_expire:
                    next_expiry_date = epoch_expire
            
        # set timeout for next check
        if next_expiry_date == float('inf'):
            self.timeout = 0
        else:
            self.timeout = int(next_expiry_date - now) + 1
    
        
    
    

from origin.neuron import Synapse, Dendrite
import subprocess, datetime, re

ALLOWED_MACS_PATH_PATTERN = 'vlan:{vlan}:allowed_macs' # sorted set with epoch expiry time (or inf) as score. ALL authorized macs are in there, even thos that expire on disconnect
DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN = 'vlan:{vlan}:disallowed_macs_on_disconnect' # set

AUTHORIZATION_CHANNEL = 'vlan_mac_authorizations'

def tzaware_datetime_to_epoch(dt):
    return (dt - datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()

def macAllowed(mac, vlan):
    return bool( Synapse().zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac) )
    # note: no need to check expiry as macs are removed when expired...

def macAuthz(mac, vlan):
    '''
        returns tuple of (datetime: until which mac is authorized, boolean: MAC should be disallowed on disconnect) 
    '''
    s = Synapse()
    return datetime.datetime.fromtimestamp(s.zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)),  s.ismember(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

def allowMAC(mac, vlan, till_date=None, disallow_mac_on_disconnect=False):
    '''
        Allow Mac on VLAN.
        if both, till_date and disallow_mac_on_disconnect, first one that occurs disallow mac.
        till_date MUST be a timezone AWARE datetime
    '''
    params = { 'mac' : mac, 'vlan': vlan, 'action': 'allow', 'disallow_mac_on_disconnect': disallow_mac_on_disconnect }
    if till_date:
        params['till_date'] = tzaware_datetime_to_epoch(till_date) # Pass as EPOCH
    Synapse().lpush(AUTHORIZATION_CHANNEL, params)
    
def disallowMAC(mac, vlan):
    Synapse().lpush(AUTHORIZATION_CHANNEL, { 'mac' : mac, 'vlan': vlan, 'action': 'disallow' } )

class MacAuthorizationManager(Dendrite):
    def __init__(self):
        super().__init__(self, 'firewall')
        
        self.add_channel(AUTHORIZATION_CHANNEL, self.handle_request)

        # get VLANS that are managed by controller.
        self.vlans = [re.search(ALLOWED_MACS_PATH_PATTERN.format(vlan='(?P<vlan>.+)'), key).group('vlan') for key in self.synapse.keys( ALLOWED_MACS_PATH_PATTERN.format(vlan='*') )]

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

    def allow_mac(self, mac, vlan, till_date, disallow_mac_on_disconnect):
        self.synapse.zadd(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), till_date, mac)
        if disallow_mac_on_disconnect:
            self.synapse.sadd(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)
        else:
            # new authorization so we we remove previous authz, if any
            self.synapse.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

        cmd = ''
        for family in ['bridge', 'ip', 'ip6']:
            cmd += 'nft add element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)

    def disallow_mac(self, mac, vlan):
        self.synapse.zrem(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)
        self.synapse.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

        cmd= ''
        for family in ['bridge', 'ip', 'ip6']:
            cmd += 'nft delete element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)
        #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)
            
    def handle_request(self, item):
        if item['action'] == 'allow':
            till_date = item.get('till_date', float('inf'))
            self.allow_mac(mac=item['mac'], vlan=item['vlan'], till_date=till_date, disallow_mac_on_disconnect=item['disallow_mac_on_disconnect'])

        else:
            self.disallow_mac(mac=item['mac'], vlan=item['vlan'])
        
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
                self.disallow_mac(mac, vlan)
            
            # get next mac to expire
            for mac, epoch_expire in self.synapse.zrange(key, 0, 0, withscores=True): # returns first mac to expire
                if next_expiry_date > epoch_expire:
                    next_expiry_date = epoch_expire
            
        # set timeout for next check
        if next_expiry_date == float('inf'):
            self.timeout = 0
        else:
            self.timeout = int(next_expiry_date - now) + 1

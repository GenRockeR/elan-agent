from origin.synapse import Synapse
import subprocess, datetime, re

ALLOWED_MACS_PATH_PATTERN = 'vlan:{vlan}:allowed_macs' # sorted set
DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN = 'vlan:{vlan}:disallowed_macs_on_disconnect' # set

AUTHORIZATION_CHANNEL = 'vlan_mac_authorizations'

def macAllowed(mac, vlan):
    return bool( Synapse().zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac) )
    # note: no need to check expiry as macs are removed when expired...

def macAuthz(mac, vlan):
    '''
        returns tuple of (datetime: until which mac is authorized, boolean: MAC should be disallowed on disconnect) 
    '''
    s = Synapse()
    return datetime.datetime.fromtimestamp(s.zscore(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)),  s.ismember(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

def allowMAC(mac, vlan, till_date=None, disallow_mac_on_disconnect=None):
    '''
        Allow Mac on VLAN.
        if none of till_date and disallow_mac_on_disconnect present, default is to disallow mac on disconnect
        if till_date and disallow_mac_on_disconnect not present, MAC will not be disallowed on disconnection
        if both, till_date and disallow_mac_on_disconnect, first one that occurs disallow mac.
        till_date MUST be a datetime
    '''
    if disallow_mac_on_disconnect is None:
        if till_date is None:
            disallow_mac_on_disconnect = True
        else:
            disallow_mac_on_disconnect = False
    
    params = { 'mac' : mac, 'vlan': vlan, 'action': 'allow', 'disallow_mac_on_disconnect': disallow_mac_on_disconnect }
    if till_date:
        params['till_date'] = till_date.strftime('%s') # Pass as EPOCH
    Synapse().lpush(AUTHORIZATION_CHANNEL, params)
    
def disallowMAC(mac, vlan):
    Synapse().lpush(AUTHORIZATION_CHANNEL, { 'mac' : mac, 'vlan': vlan, 'action': 'disallow' } )
    #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)

class FirewallConfigurator(Synapse):
    def __init__(self):
        super().__init__(self, 'firewall')
        
        self.add_channel(AUTHORIZATION_CHANNEL, self.handle_request)
        
        self.init_macs()
        
    def init_macs(self):
        # on startup, initialize sets
        # TODO: this should be done in a transaction but 'nft flush set ...' does not work... 
        cmd = ''
        for key in self.keys( ALLOWED_MACS_PATH_PATTERN.format(vlan='*')):
            m = re.search(ALLOWED_MACS_PATH_PATTERN.format(vlan='(?P<vlan>.+)'), key)
            vlan = m.group('vlan')
            for family in ['bridge', 'ip', 'ip6']:
                cmd += 'nft flush set {family} origin a_v_{vlan}'.format(family=family, vlan=vlan)
                for mac in self.zmembers(key):
                    cmd += 'nft add element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)
        
    def _save_allowed_mac(self, mac, vlan, till_date, disallow_mac_on_disconnect):
        self.zadd(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac, till_date)
        if disallow_mac_on_disconnect:
            self.sadd(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)
        else:
            # new authorization so we we remove previous authz, if any
            self.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)

    def _remove_allowed_mac(self, mac, vlan):
        self.zrem(ALLOWED_MACS_PATH_PATTERN.format(vlan=vlan), mac)
        self.srem(DISALLOWED_MACS_ON_DISCONNECT_PATH_PATTERN.format(vlan=vlan), mac)
            
    def handle_request(self, item):
        item = self.brpop(AUTHORIZATION_CHANNEL)[1]
        if item['action'] == 'allow':
            command = 'add'
            till_date = item.get('till_date', float('inf'))
            self._save_allowed_mac(mac=item['mac'], vlan=item['vlan'], till_date=till_date, disallow_mac_on_disconnect=item['disallow_mac_on_disconnect'])

        else:
            command = 'delete'
            self._remove_allowed_mac(mac=item['mac'], vlan=item['vlan'])
     
        cmd = ''
        for family in ['bridge', 'ip', 'ip6']:
            cmd += 'nft {command} element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=item['vlan'], mac=item['mac'], command=command) 
        subprocess.call(cmd, shell=True)

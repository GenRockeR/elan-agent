from origin.synapse import Synapse
import json, subprocess

ALLOWED_MACS_SETS_PATH = 'allowed_macs:'
AUTHORIZATION_CHANNEL = 'vlan_mac_authorizations'

def macAllowed(mac, vlan):
    return Synapse().sismember(ALLOWED_MACS_SETS_PATH + str(vlan), mac)

def allowMAC(mac, vlan):
    Synapse().lpush(AUTHORIZATION_CHANNEL, { 'mac' : mac, 'vlan': vlan, 'action': 'allow' } )
    
def disallowMAC(mac, vlan):
    Synapse().lpush(AUTHORIZATION_CHANNEL, { 'mac' : mac, 'vlan': vlan, 'action': 'disallow' } )

class FirewallConfigurator:
    def __init__(self):
        self.synapse = Synapse()
        self.init()
        
    def init(self):
        # on startup, initialize sets
        # TODO: this should be done in a transaction but 'nft flush set ...' does not work... 
        cmd = ''
        for key in self.synapse.keys( ALLOWED_MACS_SETS_PATH + '*'):
            for mac in self.synapse.smembers(key):
                vlan = key.replace(ALLOWED_MACS_SETS_PATH, '')
                for family in ['bridge', 'ip', 'ip6']:
                    cmd += 'nft add element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=vlan, mac=mac) 
        subprocess.call(cmd, shell=True)

    def run(self):
        while True:
            item = self.synapse.brpop(AUTHORIZATION_CHANNEL)[1]
            if item['action'] == 'allow':
                command = 'add'
                self.synapse.sadd(ALLOWED_MACS_SETS_PATH + str(item['vlan']), item['mac'])
            else:
                command = 'delete'
                self.synapse.srem(ALLOWED_MACS_SETS_PATH + str(item['vlan']), item['mac'])
            
            cmd = ''
            for family in ['bridge', 'ip', 'ip6']:
                cmd += 'nft {command} element {family} origin a_v_{vlan} {{{mac}}};'.format(family=family, vlan=item['vlan'], mac=item['mac'], command=command) 
            subprocess.call(cmd, shell=True)

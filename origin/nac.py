from origin.synapse import Synapse
import json, subprocess

ALLOWED_MACS_SETS_PATH = 'allowed_macs:'
AUTHORIZATION_CHANNEL_PATH = 'vlan_mac_authorizations:'
ALLOW_AUTHORIZATION_CHANNEL = AUTHORIZATION_CHANNEL_PATH + 'allow'
DISALLOW_AUTHORIZATION_CHANNEL = AUTHORIZATION_CHANNEL_PATH + 'disallow'

def macAllowed(mac, vlan):
    return Synapse().sismember(ALLOWED_MACS_SETS_PATH + str(vlan), mac)

def allowMAC(mac, vlan):
    Synapse().publish(ALLOW_AUTHORIZATION_CHANNEL, { 'macs' : [mac], 'vlans': [vlan] } )
    
def disallowMAC(mac, vlan):
    Synapse().publish(DISALLOW_AUTHORIZATION_CHANNEL, { 'macs' : [mac], 'vlans': [vlan] } )

class FirewallConfigurator:
    def __init__(self):
        self.synapse = Synapse()
        self.pubsub = self.synapse.pubsub() 

        self.pubsub.psubscribe([AUTHORIZATION_CHANNEL_PATH + '*'])

    def run(self):
        for item in self.pubsub.listen():
            if item['channel'] == ALLOW_AUTHORIZATION_CHANNEL or item['channel'] == DISALLOW_AUTHORIZATION_CHANNEL:
                data = json.loads(item['data']) # TODO: this should be wrapped in Synapse some way...
                if item['channel'] == DISALLOW_AUTHORIZATION_CHANNEL:
                    command = 'delete'
                else:
                    command = 'add'
                cmd = ''
                for mac in data['macs']:
                    for vlan in data['vlans']:
                        for family in ['bridge', 'ip', 'ip6']:
                            cmd += 'nft {command} element {family} origin a_v_{vlan} {mac};'.format(family=family, vlan=vlan, mac=mac, command=command) 
                subprocess.call(cmd, shell=True)
                for vlan in data['vlans']:
                    if command == 'add':
                        self.synapse.sadd(ALLOWED_MACS_SETS_PATH + str(vlan), *data['macs'])
                    else:
                        self.synapse.srem(ALLOWED_MACS_SETS_PATH + str(vlan), *data['macs'])

from origin.neuron import Dendrite, Synapse
from origin import nac
import dateutil.parser

CONF_PATH = 'conf:captive-portal'
GUEST_ACCESS_CONF_PATH = 'conf:guest-access'


def submit_guest_request(request):
    ''' submits sponsored guest access request and return ID of request'''
    d = GuestAccessManager()
    r = d.post('guest-request', request)
    request_id = r['id']
    
    d.synapse.sadd('guest-request:authz_pending:{vlan}'.format(vlan=r['vlan_id']),request['mac'])
    d.synapse.rpush('guest-request:mac_request:'+request['mac'], request_id)
    
    # Subscribe to any changes
    d.subscribe('guest-request/' + request_id)
    
    
    return request_id

def is_authz_pending(mac, vlan):
    return Synapse().sismember('guest-request:authz_pending:{vlan}'.format(vlan=vlan), mac)

class GuestAccessManager(Dendrite):
    def __init__(self):
        super().__init__('guest-access-manager')
    
    def answer_cb(self, path, answer):
        if answer['authorizations']:
            last_authz = answer['authorizations'][-1]
            mac = answer['mac']
            vlan_id = answer['vlan_id']
            
            # Authz not pending any more
            self.synapse.srem('guest-request:authz_pending:{vlan}'.format(vlan=vlan_id), mac)
            
            if last_authz['type'] == 'approval':
                if last_authz['end_authorization']:
                    till_date=dateutil.parser.parse(last_authz['end_authorization'])
                else:
                    till_date=None
                nac.allowMAC(mac, vlan_id, till_date=till_date)
            else:
                nac.disallowMAC(mac, vlan_id)
            
from origin.neuron import Dendrite
from origin import nac
import dateutil.parser

CONF_PATH = 'conf:captive-portal'
GUEST_ACCESS_CONF_PATH = 'conf:guest-access'


def submit_guest_request(request):
    ''' submits sponsored guest access request and return ID of request'''
    d = GuestAccessManager()
    r = d.post('guest-request', request)
    request_id = r['id']
    
    # Add request ID to mac -> done on retrieval of subscribe...
    #d.synapse.sadd('guest-request:'+request['mac'], request_id)
    
    # Subscribe to any changes
    d.subscribe('guest-request/' + request_id)
    
    d.synapse.lpush('guest-request:'+request['mac'], request_id) # todo: treat expired...
    
    return request_id

class GuestAccessManager(Dendrite):
    def __init__(self):
        super().__init__('guest-access-manager')
    
    def answer_cb(self, path, answer):
        if answer['authorizations']:
            last_authz = answer['authorizations'][-1]
            mac = answer['mac']
            vlan_id = answer['vlan_id']
            if last_authz['type'] == 'approval':
                nac.allowMAC(mac, vlan_id, till_date=dateutil.parser.parse(last_authz['end_authorization']))
            else:
                nac.disallowMAC(mac, vlan_id)
            
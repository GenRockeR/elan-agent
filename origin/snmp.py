from origin.neuron import Synapse, Dendrite;

SNMP_POLL_REQUEST_CHANNEL     = 'snmp:poll:request'
SNMP_DEFAULT_CREDENTIALS_PATH = 'snmp:default_credentials'

synapse = Synapse()

def snmp_poll_ip(ip, answer_path):
    synapse.lpush(SNMP_POLL_REQUEST_CHANNEL, dict(ip=ip, answer_path=answer_path))

class SnmpTracker(Dendrite):
    '''
        class responsible for receiving Traps, decoding them, and trigger according actions. (poll switch and send result to control center, notify nac of new device, etc...) 
    '''
    
    SNMP_POLL_ANSWER_CHANNEL = 'snmp:tracker:poll:answer'
    
    def __init__(self):
        super().__init__('snmp-tracker')
        self.retrieve('agent/self')
        
        self.add_channel(self.SNMP_POLL_ANSWER_CHANNEL, self.switch_data)
    
    def answer_cb(self, path, answer):
        if path == 'agent/self':
            self.snmp_credential_path = 'agent/{id}/snmp-credential'.format(id=answer['id']) 
            self.subscribe(self.snmp_credential_path)
        elif path == self.snmp_credential_path:
            self.synapse.set(SNMP_DEFAULT_CREDENTIALS_PATH, answer)
            
    def switch_data(self, data):
        self.post('switch', data)
            

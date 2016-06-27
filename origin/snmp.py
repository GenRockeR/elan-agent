from origin.neuron import Dendrite;
from origin import session, nac
from origin.event import Event
import datetime

SNMP_POLL_REQUEST_SOCK       = '/tmp/snmp-poll-request.sock'
SNMP_PARSE_TRAP_SOCK         = '/tmp/snmp-trap-parse.sock'
SNMP_NASPORT_TO_IFINDEX_SOCK = '/tmp/snmp-nasport2ifindex.sock'

SNMP_DEFAULT_CREDENTIALS_PATH   = 'snmp:default_credentials'
SNMP_READ_PARAMS_CACHE_PATH     = 'snmp:read:params'

class DeviceSnmpManager(Dendrite):
    '''
        Class for making SNMP::Info poll request on devices and to process traps. 
        It will keeping track of SNMP poll results (sending them to CC and storing them locally) 
    '''
    DEVICE_SNMP_ID_COUNTER = 'device:snmp:counter'
    DEVICE_SNMP_CACHE_PATH = 'device:snmp:id'   # polled device per ID
    DEVICE_IP_SNMP_CACHE_PATH = 'device:snmp:ip' # device ID per IP
    DEVICE_MAC_SNMP_CACHE_PATH = 'device:snmp:mac' # device ID per MAC
    DEVICE_POLL_EVERY = 600 # seconds

    def __init__(self):
        super().__init__()
    
    # retrieve from cache
    def get_new_device_id(self):
        return self.synapse.incr(self.DEVICE_SNMP_ID_COUNTER)

    def get_device_by_id(self, device_id):
        return self.synapse.hget(self.DEVICE_SNMP_CACHE_PATH, device_id)
    
    def set_device_by_id(self, device_id, device):
        return self.synapse.hset(self.DEVICE_SNMP_CACHE_PATH, device_id, device)

    def get_id_by_ip(self, ip):
        return self.synapse.hget(self.DEVICE_IP_SNMP_CACHE_PATH, ip)

    def set_id_by_ip(self, ip, device_id):
        return self.synapse.hset(self.DEVICE_IP_SNMP_CACHE_PATH, ip, device_id)

    def get_device_by_ip(self, ip):
        device_id = self.get_id_by_ip(ip)
        if device_id is None:
            return
        return self.get_device_by_id(device_id)
    
    def get_id_by_mac(self, mac):
        return self.synapse.hget(self.DEVICE_MAC_SNMP_CACHE_PATH, mac)

    def set_id_by_mac(self, mac, device_id):
        return self.synapse.hset(self.DEVICE_MAC_SNMP_CACHE_PATH, mac, device_id)

    def get_device_by_mac(self, mac):
        device_id = self.get_id_by_mac(mac)
        if device_id is None:
            return
        return self.get_device_by_id(device_id)
    
    def are_different_for_CC(self, device1, device2):
        def equal_dicts(a, b, ignore_keys):
            try:
                ka = set(a).difference(ignore_keys)
                kb = set(b).difference(ignore_keys)
                return ka == kb and all(a[k] == b[k] for k in ka)
            except:
                return False
        
        return not equal_dicts(device1, device2, ['fw_mac'])

    
    async def poll(self, ip, timeout=10):
        ''' poll and cache result'''
        device_snmp = self._poll(ip, timeout=timeout)
        
        if device_snmp is None:
            event = Event('runtime-failure', source='snmp', level='warning')
            event.add_data('ip', ip)
            event.notify()
            return
        
        # Try to find a cached device
        device_id = self.get_id_by_ip(ip)

        if not device_id and 'ports' in device_snmp:
            # Try to find cached device by mac
            for port in device_snmp['ports']:
                device_id = self.get_id_by_mac(port['mac'])
                if device_id:
                    break

        if device_id:
            cached_device = self.get_device_by_id(device_id)
        else:
            device_id = self.get_new_device_id()
            cached_device = None

        device_snmp['local_id'] = device_id
            
        # Update cached device if needed
        if cached_device != device_snmp:
            if self.are_different_for_CC(cached_device, device_snmp):
                # send update to CC if has changed
                self.post('snmp', device_snmp)
            # cache the device, including dynamic fields like fw_mac
            with self.synapse.pipeline() as pipe:
                pipe.hset( self.DEVICE_SNMP_CACHE_PATH, device_id, device_snmp )
                pipe.hset( self.DEVICE_IP_SNMP_CACHE_PATH, ip, device_id )
                cached_macs = set()
                if cached_device:
                    for port in cached_device['ports']:
                        if port['mac']:
                            cached_macs.add(port['mac'])
                device_macs = set()
                for port in device_snmp['ports']:
                    if port['mac']:
                        device_macs.add(port['mac'])
                for mac in cached_macs - device_macs: # macs not longer valid
                    pipe.hdel(self.DEVICE_MAC_SNMP_CACHE_PATH, mac)
                for mac in device_macs - cached_macs: # new macs
                    pipe.hset(self.DEVICE_MAC_SNMP_CACHE_PATH, mac, device_id)
                pipe.execute()
        return device_snmp
    
    def _parse_trap_str(self, ip, trap_str, read_params, timeout):
        answer_path = 'snmp:parse_trap:answer:{id}'.format(id=self.synapse.get_unique_id())
        self.synapse.lpush(SNMP_PARSE_TRAP_CHANNEL, dict(ip=ip, trap=trap_str, connection=read_params, answer_path=answer_path))
        r = self.synapse.brpop(answer_path, timeout=timeout)
        if r is None:
            return

        return r[1]


    def get_read_params(self, device_ip):
        # Grab SNMP read credentials of device
        read_params = self.synapse.hget(SNMP_READ_PARAMS_CACHE_PATH, device_ip)
        if not read_params:
            if self.poll(device_ip, timeout=600): # No Cached params, may take time to test them all
                read_params = self.synapse.hget(SNMP_READ_PARAMS_CACHE_PATH, device_ip)
            # TOTO: send alert to CC ON if not read_params here
        return read_params
    
    def parse_trap_str(self, trap_str, timeout=5):
        '''
        parse the trap and return 
        - trap type
        - port (ip???/interface) 
        - mac if present
        
        '''
        # if creds not known, poll switch 
        # If creds ,  parse trap,-> smart way, trying each one... and saving the matches..., 
        # -> parse trap... (create a thread just to process trap ?)
        # -> check if swicth/ switch port known and if not poll
        splitted_trap_str = trap_str.split('|',3)
        trap_time = (datetime.datetime.strptime('{} {}'.format(*splitted_trap_str[0:2]), '%Y-%m-%d %H:%M:%S') - datetime.datetime(1970, 1, 1)).total_seconds() # Epoch 
        
        snmp_connection_str = splitted_trap_str[2]
        # example of snmp_connection_str: UDP: [10.30.0.2]:56550->[10.30.0.5] -> grab what is enclosed in first brackets
        device_ip = snmp_connection_str.split(']',1)[0].split('[',1)[1]
        
        # Grab SNMP read credentials of device
        read_params = self.get_read_params(device_ip)
        if not read_params:
            return
        
        trap = self._parse_trap_str(device_ip, trap_str, read_params, timeout)
        
        if trap:
            if trap['trapType'] != 'unknown':
                '''
                Trap types: 
                  - up:
                      - trapIfIndex
                  - down 
                      - trapIfIndex
                  - mac:
                      - trapOperation:
                          - learnt
                          - removed
                          - unknown -> what do we do ? -> macsuck ?
                      - trapIfIndex
                      - trapMac
                      - trapVlan
                  - secureMacAddrViolation:
                      - trapIfIndex
                      - trapMac
                      - trapVlan
                  - dot11Deauthentication:
                      - trapMac
                  - wirelessIPS 
                      - trapMac
                  - roaming
                      - trapSSID
                      - trapIfIndex
                      - trapVlan
                      - trapMac
                      - trapClientUserName
                      - trapConnectionType
                '''
                if 'trapMac' in trap: 
                    if trap['trapType'] in ['secureMacAddrViolation', 'wirelessIPS', 'roaming'] or \
                      (trap['trapType'] == ['mac'] and trap['trapOperation'] == 'learnt'):
                        port = self.getPortFromIndex(device_ip, trap.get('trapIfIndex', None))
                        vlan=trap.get('vlan', None)
                        session.seen(trap['trapMac'], port=port, time=trap_time)
                    elif trap['trapType'] == 'dot11Deauthentication'or \
                        (trap['trapType'] == ['mac'] and trap['trapOperation'] == 'removed'):
                        nac.macDisconnected(trap['trapMac'], time=trap_time)
                # TODO: Mark Port as potentially containing a new  mac -> macksuck when new mac?
            else:
                event = Event(event_type='runtime-failure', source='snmp-notification', level='warning')
                event.add_data('ip', device_ip)
                event.notify()
                    
    
    def nasPort2IfIndexes(self, device_ip, nas_port, timeout=5):
        answer_path = 'snmp:nasport2ifindex:answer:{id}'.format(id=self.synapse.get_unique_id())
        read_params = self.get_read_params(device_ip)
        if not read_params:
            return set()
        self.synapse.lpush(SNMP_NASPORT_TO_IFINDEX_CHANNEL, dict(nas_port=nas_port, ip=device_ip, connection=read_params, answer_path=answer_path))
        r = self.synapse.brpop(answer_path, timeout=timeout)
        if r is None:
            # timeout ! return None
            return

        return set(r[1])
                    
    def getPortFromIndex(self, device_ip, if_index, force_poll=False, no_poll=False):
        '''
            Returns the port as { 'local_id': ..., 'interface':...} from given device_ip and if_index
            force_poll will force the device to be polled before resolving ifIndex to port. Else it will try to use cache.
            no_poll will disable any polling.
            Setting both no_poll and force_poll is an error. 
            Device will be polled only once, at most.
        '''
        
        if force_poll and no_poll:
            raise('Setting both no_poll and force_poll is an error.')

        if device_ip is not None and if_index is not None:
            device_polled = False
            if force_poll:
                device = self.poll(device_ip)
                device_polled = True
            else:
                device = self.get_device_by_ip(device_ip)
                if not device and not no_poll:
                    device = self.poll(device_ip)
                    device_polled = True
    
            if device:
                for port in device['ports']:
                    if port.get('index', None) == if_index:
                        return { 'local_id': device['local_id'], 'interface': port['interface']}
        
                # port not found, retry forcing poll if poll was not done
                if not device_polled and not no_poll:
                    return self.getPortFromIndex(device_ip, if_index, force_poll=True)
        
        # Device not found
        return None

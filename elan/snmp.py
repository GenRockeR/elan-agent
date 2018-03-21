import asyncio
import datetime
import json

from elan import session
from elan.event import Event, DebugEvent
from elan.neuron import Synapse, Dendrite

SNMP_POLL_REQUEST_SOCK = '/tmp/snmp-poll-request.sock'
SNMP_PARSE_TRAP_SOCK = '/tmp/snmp-trap-parse.sock'
SNMP_NASPORT_TO_IFINDEX_SOCK = '/tmp/snmp-nasport2ifindex.sock'

SNMP_DEFAULT_CREDENTIALS_PATH = 'snmp:default_credentials'
SNMP_READ_PARAMS_CACHE_PATH = 'snmp:read:params'

IGNORE_SWITCH_KEYS = (
        'fw_mac', 'fw_port', 'fw_status', 'qb_fdb_index', 'v_index', 'bp_index', 'bp_port' , 'i_vlan', 'i_untagged', 'i_vlan_membership',
        'i_vlan_membership_untagged', 'qb_i_vlan_t', 'qb_fw_mac', 'qb_fw_port', 'qb_fw_vlan', 'qb_fw_status'
)


class DeviceSnmpManager():
    '''
        Class for making SNMP::Info poll request on devices and to process traps.
        It will keeping track of SNMP poll results (notifying them and storing them locally)
    '''
    DEVICE_SNMP_ID_COUNTER = 'device:snmp:counter'
    DEVICE_SNMP_CACHE_PATH = 'device:snmp:id'  # polled device per ID
    DEVICE_IP_SNMP_CACHE_PATH = 'device:snmp:ip'  # device ID per IP
    DEVICE_MAC_SNMP_CACHE_PATH = 'device:snmp:mac'  # device ID per MAC
    DEVICE_POLL_EVERY = 600  # seconds
    DEVICE_PORTS_WITH_NEW_MAC_PATH = 'device:snmp:ports_with_new_mac'
    DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS = None
    DEVICE_PORTS_WITH_NEW_MAC_TIMEOUT = datetime.timedelta(minutes=10)

    def __init__(self):
        self.synapse = Synapse()

        now = datetime.datetime.now()
        if DeviceSnmpManager.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS is None:
            DeviceSnmpManager.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS = {
                frozenset(port.items()): now for port in self.get_ports_with_new_macs()
            }

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

    def switch_has_changed(self, device1, device2):

        def almost_equal_dicts(a, b, ignore_keys):
            try:
                ka = set(a).difference(ignore_keys)
                kb = set(b).difference(ignore_keys)
                return ka == kb and all(a[k] == b[k] for k in ka)
            except:
                return False

        # Order ports so that comparison of those lists work
        device1['ports'] = sorted(device1['ports'], key=lambda x: x.get('index', 0))
        device2['ports'] = sorted(device2['ports'], key=lambda x: x.get('index', 0))

        return not almost_equal_dicts(device1, device2, IGNORE_SWITCH_KEYS)

    async def _unix_socket_connection(self, path, data):
        reader, writer = await asyncio.open_unix_connection(path)
        writer.write(json.dumps(data).encode())
        writer.write_eof()

        response = await reader.read()

        writer.close()

        return json.loads(response.decode())

    async def _poll(self, ip):
        return await self._unix_socket_connection(SNMP_POLL_REQUEST_SOCK, dict(ip=ip))

    async def poll(self, ip, timeout=10):
        ''' poll and cache result'''
        try:
            device_snmp = await asyncio.wait_for(self._poll(ip), timeout)
        except asyncio.TimeoutError:
            device_snmp = None

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
            if cached_device is None or self.switch_has_changed(cached_device, device_snmp):
                # notify if has changed. Only send relevant keys
                Dendrite.publish_single('snmp', { k:v for k, v in device_snmp.items() if k not in IGNORE_SWITCH_KEYS })
            # cache the device, including dynamic fields like fw_mac
            with self.synapse.pipeline() as pipe:
                pipe.hset(self.DEVICE_SNMP_CACHE_PATH, device_id, device_snmp)
                pipe.hset(self.DEVICE_IP_SNMP_CACHE_PATH, ip, device_id)
                cached_macs = set()
                if cached_device:
                    for port in cached_device['ports']:
                        if port['mac']:
                            cached_macs.add(port['mac'])
                device_macs = set()
                for port in device_snmp['ports']:
                    if port['mac']:
                        device_macs.add(port['mac'])
                for mac in cached_macs - device_macs:  # macs not longer valid
                    pipe.hdel(self.DEVICE_MAC_SNMP_CACHE_PATH, mac)
                for mac in device_macs - cached_macs:  # new macs
                    pipe.hset(self.DEVICE_MAC_SNMP_CACHE_PATH, mac, device_id)
                pipe.execute()
        return device_snmp

    async def _parse_trap_str(self, ip, trap_str, read_params):

        return await self._unix_socket_connection(SNMP_PARSE_TRAP_SOCK, dict(ip=ip, trap=trap_str, connection=read_params))

    async def get_read_params(self, device_ip):
        # Grab SNMP read credentials of device
        read_params = self.synapse.hget(SNMP_READ_PARAMS_CACHE_PATH, device_ip)
        if not read_params:
            if await self.poll(device_ip, timeout=600):  # No Cached params, may take time to test them all
                read_params = self.synapse.hget(SNMP_READ_PARAMS_CACHE_PATH, device_ip)
            # TOTO: send alert to CC ON if not read_params here
        return read_params

    async def parse_trap_str(self, trap_str, timeout=5):
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
        splitted_trap_str = trap_str.split('|', 3)
        trap_time = (datetime.datetime.strptime('{} {}'.format(*splitted_trap_str[0:2]), '%Y-%m-%d %H:%M:%S') - datetime.datetime(1970, 1, 1)).total_seconds()  # Epoch

        snmp_connection_str = splitted_trap_str[2]
        # example of snmp_connection_str: UDP: [10.30.0.2]:56550->[10.30.0.5] -> grab what is enclosed in first brackets
        device_ip = snmp_connection_str.split(']', 1)[0].split('[', 1)[1]

        # Grab SNMP read credentials of device
        read_params = await self.get_read_params(device_ip)
        if not read_params:
            return

        try:
            trap = await asyncio.wait_for(self._parse_trap_str(device_ip, trap_str, read_params), timeout)
        except asyncio.TimeoutError:
            trap = None

        if trap and trap['trapType'] != 'unknown':
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
                    port = await self.getPortFromIndex(device_ip, trap.get('trapIfIndex', None))
                    vlan = trap.get('vlan', None)
                    session.seen(trap['trapMac'], vlan=vlan, port=port, time=trap_time)
                    if port is None:
                        DebugEvent(source='snmp-notification')\
                            .add_data('details', 'Port not found')\
                            .add_data('trap', trap)\
                            .add_data('trap_str', trap_str)\
                            .notify()
                elif trap['trapType'] == 'dot11Deauthentication'or \
                    (trap['trapType'] == ['mac'] and trap['trapOperation'] == 'removed'):
                    session.end(mac=trap['trapMac'], time=trap_time)
            elif trap['trapType'] in ['up', 'down']:
                port = await self.getPortFromIndex(device_ip, trap['trapIfIndex'])
                if port:
                    port['device_ip'] = device_ip
                    if trap['trapType'] == 'up':
                        # remember this port could have new ip.
                        self.port_has_new_macs(port)
                    else:
                        self.port_has_no_new_macs(port)
                        # remove macs that are no longer on port
                        mac_ports = await self.get_macs_on_device(device_ip)
                        for mac in session.port_macs(port):
                            if mac not in mac_ports:
                                session.end(mac)

            # TODO: Mark Port as potentially containing a new  mac -> macksuck when new mac?
        else:
            event = Event(event_type='runtime-failure', source='snmp-notification', level='warning')
            event.add_data('ip', device_ip)
            event.notify()

    def set_port_of_mac(self, mac):
        '''
        Will try to fond port of given
        '''
        ports_with_new_macs = self.get_ports_with_new_macs()

        if ports_with_new_macs:
            device_ips = { port.pop('device_ip') for port in ports_with_new_macs }
            for device_ip in device_ips:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                mac_ports = loop.run_until_complete(self.get_macs_on_device(device_ip))
                loop.close()
                port = mac_ports.get(mac, None)
                if port in ports_with_new_macs:
                    session.seen(mac, port=port)
                    port['device_ip'] = device_ip
                    self.port_has_no_new_macs(port)
                    break

    def port_has_new_macs(self, port):
        self.synapse.sadd(self.DEVICE_PORTS_WITH_NEW_MAC_PATH, port)
        self.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS[frozenset(port.items())] = datetime.datetime.now()
        self.expire_ports_with_new_macs()

    def port_has_no_new_macs(self, port):
        self.synapse.srem(self.DEVICE_PORTS_WITH_NEW_MAC_PATH, port)
        self.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS.pop(frozenset(port.items()), None)

    def get_ports_with_new_macs(self):
        self.expire_ports_with_new_macs()
        return self.synapse.smembers_as_list(self.DEVICE_PORTS_WITH_NEW_MAC_PATH)

    def expire_ports_with_new_macs(self):
        if DeviceSnmpManager.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS is None:
            return
        now = datetime.datetime.now()
        to_delete = []
        for f_port, timestamp in self.DEVICE_PORTS_WITH_NEW_MAC_TIMESTAMPS.items():
            if now - timestamp > self.DEVICE_PORTS_WITH_NEW_MAC_TIMEOUT:
                to_delete.append({k:v for k, v in f_port})
        for port in to_delete:
            self.port_has_no_new_macs(port)

    async def get_macs_on_device(self, device_ip):
        '''
        Will trigger an SNMP poll on device_ip
        Returns all macs on the device associated with the port they are on.
        '''
        snmp_device = await self.poll(device_ip, timeout=600)
        macs_by_if_index = {}
        fw_mac = snmp_device.get('fw_mac', {})
        for fw_hash, if_index in snmp_device.get('fw_port', {}).items():
            if fw_hash in fw_mac:
                if if_index not in macs_by_if_index:
                    macs_by_if_index[if_index] = set()
                macs_by_if_index[if_index].add(fw_mac[fw_hash])

        mac_ports = {}
        for if_index, macs in macs_by_if_index.items():
            port = await self.getPortFromIndex(device_ip, if_index)
            if port:
                for mac in macs:
                    mac_ports[mac] = port

        return mac_ports

    async def nasPort2IfIndexes(self, device_ip, nas_port, timeout=5):
        read_params = await self.get_read_params(device_ip)
        return await self._unix_socket_connection(SNMP_NASPORT_TO_IFINDEX_SOCK, dict(nas_port=nas_port, ip=device_ip, connection=read_params))

    async def getPortFromIndex(self, device_ip, if_index, force_poll=False, no_poll=False):
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
                device = await self.poll(device_ip)
                device_polled = True
            else:
                device = self.get_device_by_ip(device_ip)
                if not device and not no_poll:
                    device = await self.poll(device_ip)
                    device_polled = True

            if device:
                for port in device['ports']:
                    if port.get('index', None) == if_index:
                        return { 'local_id': device['local_id'], 'interface': port['interface']}

                # port not found, retry forcing poll if poll was not done
                if not device_polled and not no_poll:
                    return await self.getPortFromIndex(device_ip, if_index, force_poll=True)

        # Device not found
        return None

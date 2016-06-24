#!/usr/bin/env python3

from origin import session, nac, neuron, utils
from origin.event import Event, ExceptionEvent
import re
import pyshark




class DeviceTracker():
    REDIS_LIFETIME = 60 * 24 * 60 * 60 # 60 days in seconds

    def __init__(self, dendrite):
        
        self.dendrite = dendrite
        
        self.synapse = neuron.Synapse()
        
        self.interfaces = list(utils.physical_ifaces())
        
        self.dendrite.add_task(self.capture) # delay start until eventloop starts, else it seems run_in_executor starts the task straight away...

    
    def capture(self):
        for packet in pyshark.LiveCapture(
                        interface=self.interfaces,
                        bpf_filter='inbound and ( udp port 67 or arp or udp port 138 or udp port 547 or (icmp6 and ip6[40] == 0x88) or ( !ip and !ip6) )'
                    )\
                    .sniff_continuously():
            if self.stop:
                return
            self.dendrite.add_task(self.process_packet(packet))
            
        raise RuntimeError('Capture Stopped ! if it ever started...')

    async def process_packet(self, packet):
        try:
            # device sessions
            mac = packet.eth.src
            if self.ignoreMAC(mac):
                return
        
            nic = self.interfaces[int(packet.frame_info.interface_id)]
            vlan_id = 0
            packet_vlan = getattr(packet, 'vlan', None)
            if packet_vlan:
                vlan_id = packet_vlan.id 
            vlan = '{nic}.{vlan_id}'.format(nic=nic, vlan_id=vlan_id)
            epoch = int(float(packet.frame_info.time_epoch))
            
            if packet.highest_layer == 'ARP' \
                or \
               packet.highest_layer == 'ICMPV6' and packet.icmpv6.type in (136, 135): # ('Neighbor Advertisement', 'Neighbor Solicitation') 
                
                if packet.highest_layer == 'ARP':
                    ip = packet.arp.src_proto_ipv4
                else:
                    ip = packet.ipv6.src
                  
                if self.ignoreIP( ip ):
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , time=epoch)
                else:
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , ip=ip, time=epoch)
            else:
                _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , time=epoch)
        
            if vlan_added and nac.vlan_has_access_control(vlan):
                # Check Mac authorized on VLAN
                self.dendrite.add_task(self.checkAuthzOnVlan, mac, vlan)
        
            source = packet.highest_layer
            # more meaningful name
            if source == 'BROWSER':
                source = 'NetBIOS'
            elif source == 'BOOTP':
                source = 'DHCPV4'
                
                
            # DHCP fingerprint
            if source == 'DHCPV4':
                try:
                    fingerprint = { 
                                'fingerprint': ','.join(str(option.int_value) for option in packet.bootp.option_request_list_item.fields),
                                'vendor_id': str( getattr(packet.bootp, 'option_vendor_class_id', '') )
                    }
                except AttributeError:
                    pass
                else:
                    if self.isNewFingerprint(mac, fingerprint, source=source):
                        self.publish('mac/{mac}/fingerprint'.format(mac=mac, source=source), dict(source=source, **fingerprint))
            
            # Hostname: grab it from netbios or dhcpv4 or dhcpv6
            hostname = None 
            try:
                hostname = str(packet.nbdgm.source_name) # ends with <??>
                p = re.compile('<..>$')
                hostname = p.sub('', hostname)
            except AttributeError:
                try:
                    hostname = str(packet.bootp.option_hostname)
                except AttributeError:
                    try:
                        hostname = str(packet.dhcpv6.client_fqdn)
                    except AttributeError:
                        pass
            
            if hostname and self.isNewHostname(mac, hostname, source):
                self.publish('mac/{mac}/hostname'.format(mac=mac), {'name': hostname, 'source': source})

        except Exception:
            ExceptionEvent(source='network').notify()
     
    def isNewFingerprint(self, mac, fingerprint, source):
    
        key = 'mac:{mac}:fingerprint:{source}'.format(mac=mac, source=source)
        
        if self.synapse.get(key) == fingerprint:
            self.synapse.expire(key, self.REDIS_LIFETIME)
            return False
        else:
            self.synapse.set(key, fingerprint, ex=self.REDIS_LIFETIME)
            return True
    
    def isNewHostname(self, mac, hostname, source):
    
        key = 'mac:{mac}:hostname:{source}'.format(source=source, mac=mac)
    
        if self.synapse.get(key) == hostname:
            self.synapse.expire(key, self.REDIS_LIFETIME)
            return False
        else:
            self.synapse.set(key, hostname, ex=self.REDIS_LIFETIME)
            return True
    
    def ignoreMAC(self, mac):
        # Ignore broadcast packets
        if mac in ['ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00']:
            return True
    
        # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
        # name is IANA_{integer}, integer being the number of prefixed bytes.
        IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
        if mac[0:8] in IANA_6_prefix:
            return True
        IANA_4_prefix = ['33:33']
        if mac[0:5] in IANA_4_prefix:
            return True
    
        return False
    
    def ignoreIP(self, ip):
        # Ignore broadcast
        if ip[:6] == '0.0.0.' or ip in ('255.255.255.255', '::'):
            return True
        #Ignore multicast
        if ip[:4] in [str(v)+'.' for v in range(224,239)]: # 224. to 239.
            return True
        
        if ip == '::':
            return True
        
        return False
    
    def checkAuthzOnVlan(self, mac, vlan):
        authz = nac.checkAuthz(mac)
        if not authz or vlan not in authz.allow_on:
            event = Event('device-not-authorized', source='network', level='danger') 
            event.add_data('mac',  mac, data_type='mac')
            event.add_data('vlan', vlan)
            event.notify()
            # TODO: Try to move it to another vlan!
    

if __name__ == '__main__':
    p = DeviceTracker()
    p.start()


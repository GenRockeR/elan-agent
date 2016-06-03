#!/usr/bin/env python3

from origin import session, nac, neuron, utils
from origin.event import Event, ExceptionEvent
import re
import time
import pyshark
import threading


REDIS_LIFETIME = 60 * 24 * 60 * 60 # 60 days in seconds

def isNewFingerprint(mac, fingerprint, source):
    synapse = neuron.Synapse()

    key = 'mac:{mac}:fingerprint:{source}'.format(mac=mac, source=source)
    
    if synapse.get(key) == fingerprint:
        synapse.expire(key, REDIS_LIFETIME)
        return False
    else:
        synapse.set(key, fingerprint, ex=REDIS_LIFETIME)
        return True

def isNewHostname(mac, hostname, source):
    synapse = neuron.Synapse()

    key = 'mac:{mac}:hostname:{source}'.format(source=source, mac=mac)

    if synapse.get(key) == hostname:
        synapse.expire(key, REDIS_LIFETIME)
        return False
    else:
        synapse.set(key, hostname, ex=REDIS_LIFETIME)
        return True

def ignoreMAC(mac):
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

def ignoreIP(ip):
    # Ignore broadcast
    if ip[:6] == '0.0.0.' or ip in ('255.255.255.255', '::'):
        return True
    #Ignore multicast
    if ip[:4] in [str(v)+'.' for v in range(224,239)]: # 224. to 239.
        return True
    
    if ip == '::':
        return True
    
    return False

def checkAuthzOnVlan(mac, vlan):
    authz = nac.checkAuthz(mac)
    if not authz or vlan not in authz.allow_on:
        event = Event('device-not-authorized', source='network', level='danger') 
        event.add_data('mac',  mac, data_type='mac')
        event.add_data('vlan', vlan)
        event.notify()
        # TODO: Try to move it to another vlan!

    

def capture(interfaces):
    dendrite = neuron.Dendrite('device-tracker')
    
    for packet in pyshark.LiveCapture(
                    interface=interfaces,
                    bpf_filter='inbound and ( udp port 67 or arp or udp port 138 or udp port 547 or (icmp6 and ip6[40] == 0x88) or ( !ip and !ip6) )'
                )\
                .sniff_continuously():
        try:
            # device sessions
            mac = packet.eth.src
            if ignoreMAC(mac):
                return
        
            nic = interfaces[int(packet.frame_info.interface_id)]
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
                  
                if ignoreIP( ip ):
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , time=epoch)
                else:
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , ip=ip, time=epoch)
            else:
                _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan , time=epoch)
        
            if vlan_added:
                # Check Mac authorized on VLAN
                thread = threading.Thread(target=checkAuthzOnVlan, args=(mac, vlan))
                thread.start()
        
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
                    if isNewFingerprint(mac, fingerprint, source=source):
                        dendrite.post('mac/{mac}/fingerprint'.format(mac=mac, source=source), dict(source=source, **fingerprint))
            
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
            
            if hostname and isNewHostname(mac, hostname, source):
                dendrite.post('mac/{mac}/hostname'.format(mac=mac), {'name': hostname, 'source': source})

        except Exception:
            ExceptionEvent(source='network').notify()
     

if __name__ == '__main__':
    for i in range(1, 100):
        try:
            capture(list(utils.physical_ifaces()))
        except Exception:
            ExceptionEvent(source='network').notify()
            time.sleep(1)


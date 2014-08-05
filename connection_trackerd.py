#!/usr/bin/env python
import os

CONNECTION_NFLOG_QUEUE = int(os.environ.get('CONNECTION_NFLOG_QUEUE', 5))

def getPacketParams(packet, direction):
    """ Based on Impacket packet and direction, will return a dict containing LAN/WAN ether, ip, and ports if applicable, and protocol (UDP, TCP, ICMP, ICMP6, IP, IP6...).
    """
    params = {'direction': direction}
    while packet:
        if packet.__class__.__name__ == 'Ethernet':
            if direction == 'OUT':
                get_lan_ether = packet.get_ether_shost
                get_wan_ether = packet.get_ether_dhost
            elif direction == 'IN':
                get_lan_ether = packet.get_ether_dhost
                get_wan_ether = packet.get_ether_shost                    
            params['lan_mac'] = packet.as_eth_addr(get_lan_ether())
            params['wan_mac'] = packet.as_eth_addr(get_wan_ether())
        elif packet.__class__.__name__ == 'IP':
            if direction == 'OUT':
                get_lan_ip = packet.get_ip_src
                get_wan_ip = packet.get_ip_dst
            elif direction == 'IN':
                get_lan_ip = packet.get_ip_dst
                get_wan_ip = packet.get_ip_src
            params['lan_ip'] = get_lan_ip()
            params['wan_ip'] = get_wan_ip()
        elif packet.__class__.__name__ == 'IP6':
            if direction == 'OUT':
                get_lan_ip = packet.get_source_address
                get_wan_ip = packet.get_destination_address
            elif direction == 'IN':
                get_lan_ip = packet.get_destination_address
                get_wan_ip = packet.get_source_address
            params['lan_ip'] = get_lan_ip().as_string()
            params['wan_ip'] = get_wan_ip().as_string()
        elif packet.__class__.__name__ == 'UDP':
            if direction == 'OUT':
                get_lan_port = packet.get_uh_sport
                get_wan_port = packet.get_uh_dport
            elif direction == 'IN':
                get_lan_port = packet.get_uh_dport
                get_wan_port = packet.get_uh_sport
            params['lan_port'] = get_lan_port()
            params['wan_port'] = get_wan_port()
        elif packet.__class__.__name__ == 'TCP':
            if direction == 'OUT':
                get_lan_port = packet.get_th_sport
                get_wan_port = packet.get_th_dport
            elif direction == 'IN':
                get_lan_port = packet.get_th_dport
                get_wan_port = packet.get_th_sport
            params['lan_port'] = get_lan_port()
            params['wan_port'] = get_wan_port()
        
        # packet type is the last type before data.
        if packet.child().__class__.__name__ == 'Data':
            params['type'] = packet.__class__.__name__
            break
        
        packet = packet.child()
        
    else:
        #TODO: log error as we should always some data (?)
        print("Error, Data class type not found")
    return params 

def ignorePacket(pkt):
    # Ignore broadcast packets
    if pkt['wan_mac'] == 'ff:ff:ff:ff:ff:ff' or pkt['lan_mac'] == 'ff:ff:ff:ff:ff:ff':
        return True

    # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
    # name is IANA_{integer}, integer being the number of prefixed bytes.
    IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
    if pkt['wan_mac'][0:8] in IANA_6_prefix or pkt['lan_mac'][0:8] in IANA_6_prefix:
        return True
    IANA_4_prefix = ['33:33']
    if pkt['wan_mac'][0:5] in IANA_4_prefix or pkt['lan_mac'][0:5] in IANA_4_prefix:
        return True

    return False

if __name__ == '__main__':
    import time
    import origin.libnflog_cffi
    import signal
    from origin.neuron import Dendrite
    from impacket.ImpactDecoder import EthDecoder
    from origin.utils  import if_indextoname

    dendrite = Dendrite('connection-tracker')

    nflog = origin.libnflog_cffi.NFLOG().generator(CONNECTION_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'prefix', 'physindev'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
     
    for pkt, hwhdr, direction, physindev  in nflog:
        try:
            pkt_obj = decoder.decode(hwhdr + pkt)
            pkt_params = getPacketParams(pkt_obj, direction)

            if not ignorePacket(pkt_params):
                # TODO: Use NFLOG time
                pkt_params['start_time'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

                pkt_params['vlan'] = 0
                iface = if_indextoname(physindev)
                if '.' in iface:
                    pkt_params['vlan'] = iface.split('.')[1]

                dendrite.post('connection', pkt_params)

        except Exception as e:
            # TODO: notify error to central manager...
            print 'Exception: ', type(e), e




        
            

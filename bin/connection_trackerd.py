#!/usr/bin/env python
import os
from origin.event import ExceptionEvent, InternalEvent

CONNECTION_NFLOG_QUEUE = int(os.environ.get('CONNECTION_NFLOG_QUEUE', 5))

def getPacketParams(packet):
    """ Based on Impacket packet and direction, will return a dict containing LAN/WAN ether, ip, and ports if applicable, and protocol (UDP, TCP, ICMP, ICMP6, IP, IP6...).
    """
    params = {'src': {}, 'dst': {}}
    original_packet = packet
    while packet:
        if packet.__class__.__name__ == 'Ethernet':
            params['src']['mac'] = packet.as_eth_addr(packet.get_ether_shost())
            params['dst']['mac']   = packet.as_eth_addr(packet.get_ether_dhost())
        elif packet.__class__.__name__ == 'IP':
            params['src']['ip'] = packet.get_ip_src()
            params['dst']['ip']   = packet.get_ip_dst()
        elif packet.__class__.__name__ == 'IP6':
            params['src']['ip'] = packet.get_source_address().as_string()
            params['dst']['ip']   = packet.get_destination_address().as_string()
        elif packet.__class__.__name__ == 'UDP':
            params['src']['port'] = packet.get_uh_sport()
            params['dst']['port']   = packet.get_uh_dport()
        elif packet.__class__.__name__ == 'TCP':
            params['src']['port'] = packet.get_th_sport()
            params['dst']['port']   = packet.get_th_dport()
        
        # packet type is the last type before data.
        if packet.child().__class__.__name__ == 'Data':
            params['type'] = packet.__class__.__name__
            break
        
        packet = packet.child()
        
    else:
        InternalEvent( source='network')\
             .add_data('script', 'connection-tracker')\
             .add_data('details', 'Data class not found while decoding packet')\
             .add_data('packet', original_packet)\
             .notify()
    return params 

def ignorePacket(pkt):
    macs2ignore = ('ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00')
    
    for t in ('src', 'dst'):
        # Ignore broadcast packets
        if pkt[t]['mac'] in macs2ignore:
            return True
    
        # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
        # name is IANA_{integer}, integer being the number of prefixed bytes.
        IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
        if pkt[t]['mac'][0:8] in IANA_6_prefix:
            return True
        IANA_4_prefix = ['33:33']
        if pkt[t]['mac'][0:5] in IANA_4_prefix:
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

    nflog = origin.libnflog_cffi.NFLOG().generator(CONNECTION_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'physindev', 'physoutdev'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
     
    for pkt, hwhdr, physindev, physoutdev  in nflog:
        try:
            pkt_obj = decoder.decode(hwhdr + pkt)
            pkt_params = getPacketParams(pkt_obj)

            if not ignorePacket(pkt_params):
                # TODO: Use NFLOG time
                pkt_params['start_time'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

                pkt_params['src']['vlan'] = if_indextoname(physindev)
                pkt_params['dst']['vlan']   = if_indextoname(physoutdev)

                dendrite.post('connection', pkt_params)

        except Exception as e:
            ExceptionEvent(source='network')\
                 .add_data('packet', pkt)\
                 .add_data('hw_header', hwhdr)\
                 .notify()




        
            

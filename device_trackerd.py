#!/usr/bin/env python
from origin.utils import if_indextoname

LAST_SEEN_PATH = 'device:last_seen' # TODO factorize somewhere


def getPacketParams(packet):
    '''
        returns packet params:
        - mac
        - ip if present 
    '''
    params = {}
    while packet:
        if packet.__class__.__name__ == 'Ethernet':
            params['mac'] = packet.as_eth_addr(packet.get_ether_shost())
            try:
                # Todo: Treat Q in Q ....
                params['vlan'] = packet.get_tag(0).get_vid()
            except IndexError:
                params['vlan'] = 0
                
        elif packet.__class__.__name__ == 'ARP':
            if packet.get_ar_pro() == 0x800 and packet.get_ar_op() in (1,2): # IP protocol and ARP request or reply
                params['ip'] = packet.as_pro(packet.get_ar_spa())
                break
            
        elif packet.__class__.__name__ == 'IP':
            params['ip'] = packet.get_ip_src()
            break
        
        elif packet.__class__.__name__ == 'IP6':
            params['ip'] = packet.get_source_address().as_string()
            break
        
        packet = packet.child()
    return params 

def ignoreMAC(mac):
    # Ignore broadcast packets
    if mac == 'ff:ff:ff:ff:ff:ff':
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

def process_packet(pktlen, data, timestamp):
    if not data:
        return

    try:
        pkt_obj = decoder.decode(data)
        pkt_params = getPacketParams(pkt_obj)
        if ignoreMAC(pkt_params['mac']):
            return
        
        now = (datetime.datetime.fromtimestamp(timestamp) - datetime.datetime(1970, 1, 1)).total_seconds() # EPOCH

        args = [ now, dict(mac=pkt_params['mac']), 
                 now, dict(mac=pkt_params['mac'],vlan=pkt_params['vlan'])
               ]
        
        use_ip = False
        if 'ip' in pkt_params and not ignoreIP(pkt_params['ip']):
                use_ip = True
                args.extend( (now, pkt_params) )
        
        nb_added = synapse.zadd(LAST_SEEN_PATH, *args)
        
        if nb_added: # new session(s) created: inform Control Center
            if use_ip:
                session.start_IP_session(mac=pkt_params['mac'], vlan=pkt_params['vlan'], ip=pkt_params['ip'], start=now)
            else:
                session.start_VLAN_session(mac=pkt_params['mac'], vlan=pkt_params['vlan'], start=now)

    except:
        traceback.print_exc()


if __name__ == '__main__':
    import signal
    import datetime
    import traceback
    from origin.neuron import Synapse
    from origin import session
    from impacket.ImpactDecoder import EthDecoder
    import pcap
    
    synapse = Synapse()
 
    decoder = EthDecoder()
    
    p = pcap.pcapObject()
    p.open_live('eth1', 1600, 0, 100)
    p.setfilter('inbound', 0, 0)
    while 1:
        p.dispatch(1, process_packet)   


        
            

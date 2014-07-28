#!/usr/bin/env python

NFLOG_QUEUE = 10
LAST_SEEN_PATH = 'device:last_seen' # TODO factorize somewhere

import ctypes
import ctypes.util
 
libc = ctypes.CDLL(ctypes.util.find_library('c'))
 
def if_nametoindex (name):
    if not isinstance (name, str):
        raise TypeError ('name must be a string.')
    ret = libc.if_nametoindex (name)
    if not ret:
        raise RuntimeError("Invalid Name")
    return ret
     
def if_indextoname (index):
    if not isinstance (index, int):
        raise TypeError ('index must be an int.')
    libc.if_indextoname.argtypes = [ctypes.c_uint32, ctypes.c_char_p]
    libc.if_indextoname.restype = ctypes.c_char_p
     
    ifname = ctypes.create_string_buffer (32)
    ifname = libc.if_indextoname (index, ifname)
    if not ifname:
        raise RuntimeError ("Inavlid Index")
    return ifname

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


if __name__ == '__main__':
    import origin.libnflog_cffi
    import signal
    import datetime
    import traceback
    from origin.neuron import Dendrite
    from impacket.ImpactDecoder import EthDecoder
    
    dendrite = Dendrite('device-tracker')

    nflog = origin.libnflog_cffi.NFLOG().generator(NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'physindev'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
    for pkt, hwhdr, physindev  in nflog:
        try:
            pkt_obj = decoder.decode(hwhdr + pkt)
            pkt_params = getPacketParams(pkt_obj)
            if ignoreMAC(pkt_params['mac']):
                continue
            pkt_params['vlan'] = 0
            iface = if_indextoname(physindev)
            if '.' in iface:
                pkt_params['vlan'] = iface.split('.')[1]
            
            now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() # EPOCH

            args = [ now, dict(mac=pkt_params['mac']), 
                     now, dict(mac=pkt_params['mac'],vlan=pkt_params['vlan'])
                   ]
            
            use_ip = False
            if 'ip' in pkt_params and not ignoreIP(pkt_params['ip']):
                    use_ip = True
                    args.extend( (now, pkt_params) )
            
            nb_added = dendrite.synapse.zadd(LAST_SEEN_PATH, *args)
            
            if nb_added: # new session(s) created: inform Control Center
                now_str = datetime.datetime.utcfromtimestamp(now).strftime('%Y-%m-%dT%H:%M:%SZ')
                if use_ip:
                    dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}'.format(**pkt_params), {'start': now_str})
                else:
                    dendrite.post('mac/{mac}/session/current/vlan/{vlan}'.format(**pkt_params), {'start': now_str})

        except:
            traceback.print_exc()



        
            

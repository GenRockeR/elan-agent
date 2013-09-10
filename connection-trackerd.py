#!/usr/bin/env python

POST_EVERY_X_CONNECTIONS = 100
POST_EVERY_X_SECONDS = 60
 

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

def shouldLogPacket(pkt):
    # Ignore broadcast packets
    if pkt['wan_mac'] == 'ff:ff:ff:ff:ff:ff' or pkt['lan_mac'] == 'ff:ff:ff:ff:ff:ff':
        return False

    # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
    IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e']
    if pkt['wan_mac'][0:8] in IANA_6_prefix or pkt['lan_mac'][0:8] in IANA_6_prefix:
        return False

    return True
    
 
def notifyNewConnection(pkt):
    global POST_EVERY_X_CONNECTIONS, POST_EVERY_X_SECONDS
    global last_post_time, post_pool, synapse
    
    # TODO: Use NFLOG time
    pkt['start_time'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
     
    post_pool.append(pkt)
     
    if len(post_pool) >= POST_EVERY_X_CONNECTIONS or POST_EVERY_X_SECONDS <= (time.time() - last_post_time):
        # check if last request finished
        if synapse.request_finished():
            # Check how last request went on
            http_code, result = synapse.get_result()
            if http_code != 201 and http_code != 0:
                # Todo: Raise alert back to CC
                print "Error ", http_code, ': ', result
             
            if post_pool:
                synapse.start_post(post_pool)
                post_pool = []
 

if __name__ == '__main__':
    import time
    import origin.libnflog_cffi
    import signal
    from origin.synapse import Synapse
    from impacket.ImpactDecoder import EthDecoder
    
    last_post_time = time.time()
    post_pool = []
    
    synapse = Synapse(path = 'connection')

    nflog = origin.libnflog_cffi.NFLOG().generator(0, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
     
    # catch TERM signal so final post can execute.
    def noop(signum, frame):
        pass
    signal.signal(signal.SIGTERM, noop)
    
    
    try:
        for pkt, hwhdr, direction  in nflog:
            try:
                pkt_obj = decoder.decode(hwhdr + pkt)
                pkt_params = getPacketParams(pkt_obj, direction)
                if shouldLogPacket(pkt_params):
                    notifyNewConnection(pkt_params)
            except Exception as e:
                # TODO: notify error to central manager...
                print 'Exception: ', type(e), e
    finally:
        # Let request finish and send remaining connections, if any
        http_code, result = synapse.get_result()
        if http_code != 201 and http_code != 0:
            # Todo: Raise alert back to CC
            print "Error ", http_code, ': ', result
        else:
            post_pool = []
        if post_pool:
            synapse.post(post_pool)




        
            

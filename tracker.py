#!/usr/bin/env python
from impacket.ImpactDecoder import EthDecoder
import libnflog_cffi
import time

class Tracker():
    def __init__(self, connection_ttl_mn = 10):
        self.establisedConnections = Connection_tree()
        self.decoder = EthDecoder()
        self.connection_ttl_mn = connection_ttl_mn # used when calling cleanupEstablishedConnexions
        self.lastEstablishedConnexionsCleanup = time.time()
        self.leaves_count = 0
    
    def notifyNewConnection(self, packet):
        if self.leaves_count % 1000 == 0:
            print self.leaves_count,
        
    def cleanupEstablishedConnexions(self):
        print
        print 'total leaves before: ' + str(self.leaves_count),
        self.__cleanupEstablishedConnexions(self.establisedConnections)
        print 'total leaves after : ' + str(self.leaves_count)
        self.lastEstablishedConnexionsCleanup = time.time()
        
        
    def __cleanupEstablishedConnexions(self, tree):
        trash = {}
        for branch in tree:
            subtree = tree[branch]
            if type(subtree).__name__ == 'Connection_tree':
                self.__cleanupEstablishedConnexions(subtree)
                if len(subtree) == 0:
                    trash[branch] = tree
            elif subtree['last_seen'] < (time.time() - 60 * self.connection_ttl_mn):
                trash[branch] = tree
                self.leaves_count -= 1
        # Delete after so dict not changed during iteration
        for key in trash:
            del trash[key][key] # trash[key] give the dict from wich we want to delete 'key' entry
        
    def processPacket(self, pktBuffer, direction):
        """ Reads a packet buffer, decodes its and if first time time that connection seen, tells central Controller.
        As the direction is known, packet will be tracked from the inner IP.
        
        """

        packet = self.decoder.decode(pktBuffer)
        pkt_params = self.getPacketParams(packet, direction)
        # check if connection has ports defined
        if 'lan_port' in pkt_params:
            connection_path = self.establisedConnections[ pkt_params['lan_ip'] ][ pkt_params['wan_ip'] ][ pkt_params['lan_port'] ][ pkt_params['wan_port'] ]
        else:
            connection_path = self.establisedConnections[ pkt_params['lan_ip'] ][ pkt_params['wan_ip'] ]
        
        now = time.time()
        if pkt_params['type'] in connection_path:
            connection_path[ pkt_params['type'] ][ 'length' ] += len(pktBuffer)
            connection_path[ pkt_params['type'] ][ 'last_seen' ] = now
        else:
            connection_path[ pkt_params['type'] ] = {
                    'length': len(pktBuffer),
                    'direction': direction,
                    'first_seen': now,
                    'last_seen': now,
                    'lan_ether': pkt_params['lan_ether'],
                    'wan_ether': pkt_params['wan_ether']
            }
            self.leaves_count += 1
            self.notifyNewConnection(pkt_params)

    def getPacketParams(self, packet, direction):
        """ Base on Impacket packet and direction, will return a dict containing LAN/WAN ether, ip, and port if applicable, and protocol (UDP, TCP, ICMP, UDP6...).
        """
        params = {}
        while packet:
            if packet.__class__.__name__ == 'Ethernet':
                if direction == 'OUT':
                    get_lan_ether = packet.get_ether_shost
                    get_wan_ether = packet.get_ether_dhost
                elif direction == 'IN':
                    get_lan_ether = packet.get_ether_dhost
                    get_wan_ether = packet.get_ether_shost                    
                params['lan_ether'] = packet.as_eth_addr(get_lan_ether())
                params['wan_ether'] = packet.as_eth_addr(get_wan_ether())
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
            #TODO: log error as we should always some date (?)
            print("Error, Data class type not found")
        return params 

class Connection_tree(dict):
    """Implementation of perl's auto-vivification feature for dict."""
    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value


if __name__ == "__main__":
    nflog = libnflog_cffi.NFLOG().generator(0, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)

    tracker = Tracker()
    
    for pkt, hwhdr, direction  in nflog:
        try:
            tracker.processPacket( hwhdr + pkt, direction )
            if tracker.lastEstablishedConnexionsCleanup < time.time() - 60 * 1: # every 1 mn
                tracker.cleanupEstablishedConnexions()
        except Exception as e:
            # TODO: notify error to central manager...
            print 'Error: ' + str(e)
            
            

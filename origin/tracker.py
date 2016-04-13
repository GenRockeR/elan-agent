#!/usr/bin/env python
from impacket.ImpactDecoder import EthDecoder
import time
from origin.event import InternalEvent

class Tracker():
    def __init__(self, new_connection_cb = None, deleted_connection_cb = None, connection_ttl_mn = 10):
        self.establisedConnections = Connection_tree()
        self.decoder = EthDecoder()
        self.lastEstablishedConnexionsCleanup = time.time()
        self.leaves_count = 0
        self.macIPs = {}
        
        self.connection_ttl_mn = connection_ttl_mn          # timeout to consider connection as closed if no new traffic seen.
        self.new_connection_cb = new_connection_cb          # callback function when new connection found.
        self.deleted_connection_cb = deleted_connection_cb  # callback function when connection deleted from established connection table.
    
    def cleanupEstablishedConnexions(self):
        self.__cleanupEstablishedConnexions(self.establisedConnections)
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
                if self.deleted_connection_cb:
                    self.deleted_connection_cb(subtree)
        # Delete after, so dict does not change during iteration
        for key in trash:
            del trash[key][key] # trash[key] gives the dict from which we want to delete 'key' entry
        
    def processPacket(self, pktBuffer, direction):
        """ Reads a packet buffer, decodes its and if first time time that connection seen, tells central Controller.
        As the direction is known, packet will be tracked from the inner IP.
        
        """
        packet = self.decoder.decode(pktBuffer)
        pkt_params = self.getPacketParams(packet, direction)
        # check if connection has ports defined
        try:
            if 'lan_port' in pkt_params:
                type_path = self.establisedConnections[ pkt_params['lan_ip'] ][ pkt_params['wan_ip'] ][ pkt_params['lan_port'] ][ pkt_params['wan_port'] ]
            else:
                type_path = self.establisedConnections[ pkt_params['lan_ip'] ][ pkt_params['wan_ip'] ]
        except KeyError:
            # if not IP stack
            return

        now = time.time()

        if pkt_params['type'] in type_path:
            type_path[ pkt_params['type'] ]['size'] += len(pktBuffer)
            type_path[ pkt_params['type'] ]['last_seen'] = now
        else:
            pkt_params['first_seen'] = now
            pkt_params['direction'] = direction
            type_path[ pkt_params['type'] ] = pkt_params
            self.leaves_count += 1
            if self.new_connection_cb:
                self.new_connection_cb(type_path[ pkt_params['type'] ])
            pkt_params['size'] = len(pktBuffer)
            pkt_params['last_seen'] = now

    def getPacketParams(self, packet, direction):
        """ Based on Impacket packet and direction, will return a dict containing LAN/WAN ether, ip, and ports if applicable, and protocol (UDP, TCP, ICMP, ICMP6, IP, IP6...).
        """
        params = { 'lan': {}, 'wan': {}}
        original_packet = packet
        while packet:
            if packet.__class__.__name__ == 'Ethernet':
                if direction == 'OUT':
                    get_lan_ether = packet.get_ether_shost
                    get_wan_ether = packet.get_ether_dhost
                elif direction == 'IN':
                    get_lan_ether = packet.get_ether_dhost
                    get_wan_ether = packet.get_ether_shost                    
                params['lan']['mac'] = packet.as_eth_addr(get_lan_ether())
                params['wan']['mac'] = packet.as_eth_addr(get_wan_ether())
            elif packet.__class__.__name__ == 'IP':
                if direction == 'OUT':
                    get_lan_ip = packet.get_ip_src
                    get_wan_ip = packet.get_ip_dst
                elif direction == 'IN':
                    get_lan_ip = packet.get_ip_dst
                    get_wan_ip = packet.get_ip_src
                params['lan']['ip'] = get_lan_ip()
                params['wan']['ip'] = get_wan_ip()
            elif packet.__class__.__name__ == 'IP6':
                if direction == 'OUT':
                    get_lan_ip = packet.get_source_address
                    get_wan_ip = packet.get_destination_address
                elif direction == 'IN':
                    get_lan_ip = packet.get_destination_address
                    get_wan_ip = packet.get_source_address
                params['lan']['ip'] = get_lan_ip().as_string()
                params['wan']['ip'] = get_wan_ip().as_string()
            elif packet.__class__.__name__ == 'UDP':
                if direction == 'OUT':
                    get_lan_port = packet.get_uh_sport
                    get_wan_port = packet.get_uh_dport
                elif direction == 'IN':
                    get_lan_port = packet.get_uh_dport
                    get_wan_port = packet.get_uh_sport
                params['lan']['port'] = get_lan_port()
                params['wan']['port'] = get_wan_port()
            elif packet.__class__.__name__ == 'TCP':
                if direction == 'OUT':
                    get_lan_port = packet.get_th_sport
                    get_wan_port = packet.get_th_dport
                elif direction == 'IN':
                    get_lan_port = packet.get_th_dport
                    get_wan_port = packet.get_th_sport
                params['lan']['port'] = get_lan_port()
                params['wan']['port'] = get_wan_port()
            
            # packet type is the last type before data.
            if packet.child().__class__.__name__ == 'Data':
                params['type'] = packet.__class__.__name__
                break
            
            packet = packet.child()
            
        else:
            InternalEvent(source='network')\
                     .add_data('script', 'connection-tracker')\
                     .add_data('details', 'Data class not found while decoding packet')\
                     .add_data('packet', original_packet)\
                     .notify()
        return params 

class Connection_tree(dict):
    """Implementation of perl's auto-vivification feature for dict."""
    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            value = self[item] = type(self)()
            return value

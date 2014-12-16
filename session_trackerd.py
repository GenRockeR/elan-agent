#!/usr/bin/env python
import socket
from impacket.ImpactPacket import EthernetTag, Ethernet, ARP
from impacket.IP6_Address import IP6_Address
from impacket.IP6 import IP6
from impacket.NDP import NDP, NDP_Option
from origin.utils import get_ip4_address, get_ip6_address, get_ether_address
from origin import session

LAST_SEEN_PATH = 'device:macs:last_seen'
SESSION_END_NOTIFICATION_PATH = 'device:session_end_notification'
DISCONNECT_NOTIFICATION_PATH = 'device:vlan_mac_disconnected' # TODO Factorize: also in nac

PING_OBJECTS_AFTER = 240    #  4 minutes
PING_EVERY = 10             # 10 seconds
EXPIRY_OBJECT_AFTER = 300   #  5 minutes

def pingIP(mac, vlan, ip):
    if ':' in ip:
        ndpPing(mac, vlan, ip)
    else:
        arpPing(mac, vlan, ip)


def ndpPing(dst_mac, vlan, dst_ip):
    src_mac = get_ether_address('br0')

    if_name = 'eth1'

    src_ip = get_ip6_address('br0')['address']

    ethernet = Ethernet()
    ethernet.set_ether_shost( tuple(int(v,16) for v in src_mac.split(':')) )
    ethernet.set_ether_dhost( tuple(int(v,16) for v in dst_mac.split(':')) )

    if vlan:
        tag = EthernetTag()
        tag.set_vid(int(vlan))
        ethernet.push_tag(tag)


    ip6 = IP6()
    ip6.set_source_address(src_ip)
    ip6.set_destination_address(dst_ip)
    ip6.set_traffic_class(0)
    ip6.set_flow_label(0)
    ip6.set_hop_limit(255)

    ndp = NDP.Neighbor_Solicitation(IP6_Address(dst_ip))
    ndp.append_ndp_option(NDP_Option.Source_Link_Layer_Address(ethernet.get_ether_shost()))

    ip6.contains(ndp)
    ip6.set_next_header(ip6.child().get_ip_protocol_number())
    ip6.set_payload_length(ip6.child().get_size())

    ethernet.contains(ip6)

    ndp.calculate_checksum()

    s = socket.socket(socket.PF_PACKET, socket.SOCK_RAW, socket.SOCK_RAW)
    s.bind((if_name, socket.SOCK_RAW))
    s.send(ethernet.get_packet())


    
def arpPing(mac, vlan, ip):    
    if_name = 'eth1'

    ethernet = Ethernet()
    ethernet.set_ether_shost( tuple(int(v,16) for v in get_ether_address('br0').split(':')) )
    ethernet.set_ether_dhost( tuple(int(v,16) for v in mac.split(':')) )

    if vlan:
        tag = EthernetTag()
        tag.set_vid(int(vlan))
        ethernet.push_tag(tag)

    arp = ARP()
    
    arp.set_ar_pro(0x800) # IP
    arp.set_ar_hln(6) # protocol address length (IP)
    arp.set_ar_pln(4) # link layer address length (ethernet)
    arp.set_ar_op(1) # Arp request
    arp.set_ar_hrd(1) # ethernet
    arp.set_ar_spa( tuple(int(v) for v in get_ip4_address('br0')['address'].split('.')) )
    arp.set_ar_tpa( tuple(int(v) for v in ip.split('.')) )

    ethernet.contains(arp)

    s = socket.socket(socket.PF_PACKET, socket.SOCK_RAW, socket.SOCK_RAW)
    s.bind((if_name, socket.SOCK_RAW))
    s.send(ethernet.get_packet())

def getSecondsBeforeNextCheck(dendrite, now=None):
    if not now:
        now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() # EPOCH
    nextobj_arr = dendrite.synapse.zrange(LAST_SEEN_PATH, 0, 0, withscores=True)
    if nextobj_arr:
        last_seen = nextobj_arr[0][1]
        if last_seen + PING_OBJECTS_AFTER <= now:
            return PING_EVERY
        else:
            return int(last_seen + PING_OBJECTS_AFTER - now) + 1 # can be 0 if PING_OBJECTS_AFTER + last_seen slightly higher than now 0.1sec for ex.
    else:
        # No objects to be watched, we can sleep for PING_OBJECTS_AFTER
        return PING_OBJECTS_AFTER

def notify_disconnection(dendrite, **kwargs):
    dendrite.synapse.lpush(DISCONNECT_NOTIFICATION_PATH, kwargs)
    
def check_session(dendrite):
    now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() # EPOCH
    synapse = dendrite.synapse


    # Use pipeline to delete and retrieve all objects that have expired...
    pipe = synapse.pipe
    pipe.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - EXPIRY_OBJECT_AFTER)
    pipe.zremrangebyscore(LAST_SEEN_PATH, float('-inf'), now - EXPIRY_OBJECT_AFTER)
    expired_objects = pipe.execute()[0]
    #TODO: used last seen time (score) as end of sessions rather than now
    
    
    # Expire all objects
    # Don't send expire if object level up has expired as it will be done on its own
    mac_expired = []
    vlan_expired = []
    ip_expired = []
    for obj in expired_objects:
        if 'ip' in obj:
            ip_expired.append(obj)
        elif 'vlan' in obj:
            vlan_expired.append(obj)
        else:
            mac_expired.append(obj)

    for obj in ip_expired:
        if {'mac': obj['mac'], 'vlan': obj['vlan']} not in vlan_expired and {'mac': obj['mac']} not in mac_expired:
            session.notify_end_IP_session(end=now, **obj)

    for obj in vlan_expired:
        if {'mac': obj['mac']} not in mac_expired:
            session.notify_end_VLAN_session(end=now, **obj)
        # Notify device disconnected from VLAN
        notify_disconnection(dendrite, mac=obj['mac'], vlan=obj['vlan'])

    for obj in mac_expired:
        session.remove_till_disconnect_authentication_session(obj['mac'])
        session.notify_end_MAC_session(end=now, **obj)


    # ping Objects
    for obj in synapse.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - PING_OBJECTS_AFTER):
        if 'ip' in obj:
            pingIP(**obj)
        else:
            pass # Can not ping a MAC without an IP. MAC, VLAN are just there to know that the session has ended...
        
    # Set Timeout for next  check
    dendrite.timeout = getSecondsBeforeNextCheck(dendrite, now)
    

def process_notification(dendrite):
    pass
    
if __name__ == '__main__':
    import signal # Todo: clean exit...
    import datetime, time, traceback
    from origin.neuron import Dendrite
    
    dendrite = Dendrite('session-tracker', timeout_cb=check_session, timeout=1) # make it run almost straight away on first run
    dendrite.add_channel(SESSION_END_NOTIFICATION_PATH, process_notification)
    
    count = 0
    while count < 100:
        try:
            dendrite.run_for_ever()
        except:
            traceback.print_exc()
            time.sleep(1) # avoid locking CPU if exception on each loop
            dendrite.timeout = 4
            count = count + 1


            

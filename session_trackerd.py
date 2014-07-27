#!/usr/bin/env python
import socket, fcntl, struct
from impacket.ImpactPacket import Ethernet, ARP

LAST_SEEN_PATH = 'device:last_seen' # TODO factorize somewhere
SESSION_NOTIFICATION_PATH = 'device:session_notification'

PING_OBJECTS_AFTER = 240    #  4 minutes
PING_EVERY = 10             # 10 seconds
EXPIRY_OBJECT_AFTER = 300   #  5 minutes

def expireIP( mac, vlan, ip ):
    print('expireIP', mac, vlan, ip)
    

def expireVLAN( mac, vlan ):
    print('expireVLAN', mac, vlan)

def expireMAC( mac ):
    print('expireMAC', mac)

def pingIP(mac, vlan, ip):
    if '.' in ip:
        print('Ping ipv4', mac, vlan, ip)
        arpPing(mac, vlan, ip)
    else:
        print('Ping ipv6', mac, vlan, ip)
    
def arpPing(mac, vlan, ip):    
    s = socket.socket(socket.PF_PACKET, socket.SOCK_RAW, socket.SOCK_RAW)
    if_name = 'eth1'
    if vlan:
        if_name += '.' + vlan
    s.bind((if_name, socket.SOCK_RAW))

    ethernet = Ethernet()
    arp = ARP()
    
    arp.set_ar_pro(0x800) # IP
    arp.set_ar_hln(6) # protocol address length (IP)
    arp.set_ar_pln(4) # link layer address length (ethernet)
    arp.set_ar_op(1) # Arp request
    arp.set_ar_hrd(1) # ethernet
    arp.set_ar_spa( tuple(int(v) for v in get_ip_address('br0').split('.')) )
    arp.set_ar_tpa( tuple(int(v) for v in ip.split('.')) )

    ethernet.contains(arp)
    ethernet.set_ether_shost( tuple(int(v,16) for v in getHwAddr('br0').split(':')) )
    ethernet.set_ether_dhost( tuple(int(v,16) for v in mac.split(':')) )

    s.send(ethernet.get_packet())

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack( '256s', ifname[:15] )
    )[20:24])

def getHwAddr(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927,  struct.pack('256s', ifname[:15]))
    return ''.join(['%02x:' % ord(char) for char in info[18:24]])[:-1]

def getSecondsBeforeNextCheck(dendrite, now):   
    nextobj_arr = dendrite.synapse.zrange(LAST_SEEN_PATH, 0, 0, withscores=True)
    if nextobj_arr:
        last_seen = nextobj_arr[0][1]
        if last_seen + PING_OBJECTS_AFTER < now:
            return PING_EVERY
        else:
            return int(PING_OBJECTS_AFTER + last_seen - now)
    else:
        # No objects to be watched, we can sleep for PING_OBJECTS_AFTER
        return PING_OBJECTS_AFTER

def check_session(dendrite):
    now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() # EPOCH
    now_str = datetime.datetime.utcfromtimestamp(now).strftime('%Y-%m-%dT%H:%M:%SZ')
    synapse = dendrite.synapse

    # Expire all objects
    # Don't send expire if object level up has expire as it will be done on its own
    mac_expired = set()
    vlan_expired = set()
    ip_expired = set()
    for obj in synapse.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - EXPIRY_OBJECT_AFTER):
        if 'ip' in obj:
            ip_expired.add(obj)
        elif 'vlan' in obj:
            vlan_expired.add(obj)
        else:
            mac_expired.add(obj)

    for obj in ip_expired:
        if {'mac': obj['mac'], 'vlan': obj['vlan']} not in vlan_expired and {'mac': obj['mac']} not in mac_expired:
            dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/ip/{ip}/current/end'.format(**obj), {'end': now_str})
        synapse.zrem(LAST_SEEN_PATH, obj)
    for obj in vlan_expired:
        if {'mac': obj['mac']} not in mac_expired:
            dendrite.post('mac/{mac}/session/current/vlan/{vlan}/current/end'.format(**obj), {'end': now_str})
        synapse.zrem(LAST_SEEN_PATH, obj)
    for obj in mac_expired:
        dendrite.post('mac/{mac}/session/current/end'.format(**obj), {'end': now_str})
        synapse.zrem(LAST_SEEN_PATH, obj)

    # ping Objects
    for obj in synapse.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - PING_OBJECTS_AFTER):
        if 'ip' in obj:
            pingIP(**obj)
        else:
            pass # Can not ping a MAC without an IP. MAC, VLAN are just there to know that the session has ended...
        
    # Set Timeout for next  check
    dendrite.timeout = getSecondsBeforeNextCheck(dendrite.now)
    

def process_notification(dendrite):
    pass
    
if __name__ == '__main__':
    import signal # Todo: clean exit...
    import datetime, time, traceback
    from origin.neuron import Dendrite
    
    dendrite = Dendrite('session-tracker', timeout_cb=check_session)
    dendrite.add_channel(SESSION_NOTIFICATION_PATH, process_notification)
    
    count = 0
    while count < 100:
        try:
            dendrite.run_for_ever()
        except:
            traceback.print_exc()
            time.sleep(1) # avoid locking CPU if exception on each loop
            dendrite.timeout = 4
            count = count + 1


            

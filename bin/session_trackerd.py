#!/usr/bin/env python3
import datetime
import time

from scapy.all import sendp, Ether, ARP, Dot1Q, IPv6, ICMPv6ND_NS

from elan import session
from elan.neuron import Synapse
from elan.utils import get_ip4_address, get_ip6_address, get_ether_address

LAST_SEEN_PATH = 'device:macs:last_seen'

PING_OBJECTS_AFTER = 240  #  4 minutes
PING_EVERY = 10  # 10 seconds
EXPIRY_OBJECT_AFTER = 300  #  5 minutes


def pingIP(mac, vlan, ip):
    if ':' in ip:
        ndpPing(mac, vlan, ip)
    else:
        arpPing(mac, vlan, ip)


def ndpPing(mac, vlan, ip):
    src_mac = get_ether_address('br0')
    packet = Ether(src=src_mac, dst=mac)

    if_name = vlan
    if '.' in vlan:
        if_name, vlan_id = vlan.rsplit('.', 1)
        vlan_id = int(vlan_id)
        if vlan_id:
            packet = packet / Dot1Q(vlan=vlan_id)

    src_ip = get_ip6_address('br0')['address']
    if src_ip is None:
        src_ip = 'fe80::66:66'  # we need a source IP...
    packet = packet / IPv6(src=src_ip, dst=ip)
    packet = packet / ICMPv6ND_NS(tgt=ip)

    sendp(packet, iface=if_name)


def arpPing(mac, vlan, ip):
    src_mac = get_ether_address('br0')
    packet = Ether(src=src_mac, dst=mac)

    if_name = vlan
    if '.' in vlan:
        if_name, vlan_id = vlan.rsplit('.', 1)
        vlan_id = int(vlan_id)
        if vlan_id:
            packet = packet / Dot1Q(vlan=vlan_id)

    src_ip = get_ip4_address('br0')['address']
    if src_ip is None:
        src_ip = '169.254.66.66'  # we need a source IP...
    packet = packet / ARP(hwsrc=src_mac, psrc=src_ip, hwdst=mac, pdst=ip)

    sendp(packet, iface=if_name)


class SessionTracker():

    def __init__(self):
        self.synapse = Synapse()

    def run(self):
        while True:
            self.check_sessions()
            wait_time = self.getSecondsBeforeNextCheck()
            if(wait_time > 0):
                time.sleep(wait_time)

    def check_sessions(self):
        now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # EPOCH

        expired_objects = self.synapse.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - EXPIRY_OBJECT_AFTER, withscores=True)

        # Expire all objects
        # Don't send expire if object level up has expired as it will be done on its own
        expired_macs = []
        expired_vlans = []
        expired_ips = []
        last_seen_macs = []
        last_seen_vlans = []
        last_seen_ips = []

        for obj, last_seen in expired_objects:
            if 'ip' in obj:
                expired_ips.append(obj)
                last_seen_ips.append((obj, last_seen))
            elif 'vlan' in obj:
                expired_vlans.append(obj)
                last_seen_vlans.append((obj, last_seen))
            else:
                expired_macs.append(obj)
                last_seen_macs.append((obj, last_seen))

        for obj, last_seen in last_seen_ips:
            if {'mac': obj['mac'], 'vlan': obj['vlan']} not in expired_vlans and {'mac': obj['mac']} not in expired_macs:
                session.end(time=int(last_seen), **obj)

        for obj, last_seen in last_seen_vlans:
            if {'mac': obj['mac']} not in expired_macs:
                session.end(time=last_seen, **obj)

        for obj, last_seen in last_seen_macs:
            # Consider Mac as disconnected...
            session.end(mac=obj['mac'], time=last_seen)

        # ping Objects
        for obj in self.synapse.zrangebyscore(LAST_SEEN_PATH, float('-inf'), now - PING_OBJECTS_AFTER):
            if 'ip' in obj:
                pingIP(**obj)
            else:
                pass  # Can not ping a MAC without an IP. MAC, VLAN are just there to know that the session has ended...

    def getSecondsBeforeNextCheck(self, now=None):
        if not now:
            now = (datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds()  # EPOCH
        nextobj_arr = self.synapse.zrange(LAST_SEEN_PATH, 0, 0, withscores=True)
        if nextobj_arr:
            last_seen = nextobj_arr[0][1]
            if last_seen + PING_OBJECTS_AFTER <= now:
                return PING_EVERY
            else:
                return int(last_seen + PING_OBJECTS_AFTER - now) + 1  # can be 0 if PING_OBJECTS_AFTER + last_seen slightly higher than now 0.1sec for ex.
        else:
            # No objects to be watched, we can sleep for PING_OBJECTS_AFTER
            return PING_OBJECTS_AFTER


if __name__ == '__main__':

    tracker = SessionTracker()
    tracker.run()


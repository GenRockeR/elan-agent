#!/usr/bin/env python3

import re
import threading

import pyshark

from elan import session, nac, neuron, utils, device
from elan.event import Event, ExceptionEvent


class DeviceTracker():

    def __init__(self):

        self.dendrite = neuron.Dendrite()

        self.synapse = neuron.Synapse()

        self.interfaces = list(utils.physical_ifaces())

    def capture(self):
        for packet in pyshark.LiveCapture(
                        interface=self.interfaces,
                        bpf_filter='inbound and ( udp port 67 or arp or udp port 138 or udp port 547 or (icmp6 and ip6[40] == 0x88) or ( !ip and !ip6) )'
                    )\
                    .sniff_continuously():
            self.process_packet(packet)

        raise RuntimeError('Capture Stopped ! if it ever started...')

    def process_packet(self, packet):
        try:
            # device sessions
            mac = packet.eth.src
            if session.ignore_MAC(mac):
                return

            nic = self.interfaces[int(packet.frame_info.interface_id)]
            vlan_id = 0
            packet_vlan = getattr(packet, 'vlan', None)
            if packet_vlan:
                vlan_id = packet_vlan.id
            vlan = '{nic}.{vlan_id}'.format(nic=nic, vlan_id=vlan_id)
            epoch = int(float(packet.frame_info.time_epoch))

            if packet.highest_layer == 'ARP' \
                or \
               packet.highest_layer == 'ICMPV6' and str(packet.icmpv6.type) in ('136', '135'):  # ('Neighbor Advertisement', 'Neighbor Solicitation')

                if packet.highest_layer == 'ARP':
                    ip = packet.arp.src_proto_ipv4
                else:
                    ip = packet.ipv6.src

                if session.ignore_IP(ip):
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, time=epoch)
                else:
                    _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, ip=ip, time=epoch)
            else:
                _mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, time=epoch)

            if vlan_added and nac.vlan_has_access_control(vlan):
                # Check Mac authorized on VLAN
                task = threading.Thread(target=self.checkAuthzOnVlan, args=(mac, vlan))
                task.start()

            source = packet.highest_layer
            # more meaningful name
            if source == 'BROWSER':
                source = 'NetBIOS'
            elif source == 'BOOTP':
                source = 'DHCPV4'

            # DHCP fingerprint
            if source == 'DHCPV4':
                try:
                    fingerprint = {
                                'fingerprint': ','.join(str(option.int_value) for option in packet.bootp.option_request_list_item.fields),
                                'vendor_id': str(getattr(packet.bootp, 'option_vendor_class_id', ''))
                    }
                except AttributeError:
                    pass
                else:
                    device.seen_fingerprint(mac, fingerprint, source)

            # Hostname: grab it from netbios or dhcpv4 or dhcpv6
            hostname = None
            try:
                hostname = str(packet.nbdgm.source_name)  # ends with <??>
                p = re.compile('<..>$')
                hostname = p.sub('', hostname)
            except AttributeError:
                try:
                    hostname = str(packet.bootp.option_hostname)
                except AttributeError:
                    try:
                        hostname = str(packet.dhcpv6.client_fqdn)
                    except AttributeError:
                        pass

            if hostname:
                device.seen_hostname(mac, hostname, source)

        except Exception:
            ExceptionEvent(source='network').notify()

    def checkAuthzOnVlan(self, mac, vlan):
        authz = nac.checkAuthz(mac)
        if not authz or vlan not in authz.allow_on:
            event = Event('device-not-authorized', source='network', level='danger')
            event.add_data('mac', mac, data_type='mac')
            event.add_data('vlan', vlan)
            event.notify()
            # TODO: Try to move it to another vlan!


if __name__ == '__main__':
    p = DeviceTracker()
    p.capture()


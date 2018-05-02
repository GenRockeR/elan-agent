#!/usr/bin/env python3

import functools
import re
import threading

from elan import session, nac, neuron, utils, device
from elan.capture import Capture
from elan.event import Event, ExceptionEvent
from elan.snmp import DeviceSnmpManager


class DeviceTracker():

    def __init__(self):

        self.dendrite = neuron.Dendrite()

        self.synapse = neuron.Synapse()

        self.interfaces = list(utils.physical_ifaces())

    def capture(self):
        capture = Capture(
                name='device-tracker',
                interface=self.interfaces,
                capture_filter='inbound and ( udp port 67 or arp or udp port 138 or udp port 547 or (icmp6 and ip6[40] == 0x88) or (udp src port 5353 and udp dst port 5353) or ( !ip and !ip6) )'
        )

        capture.remove_files()

        for packet in capture:
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
                    mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, time=epoch)
                else:
                    mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, ip=ip, time=epoch)
            else:
                mac_added, vlan_added, _ip_added = session.seen(mac, vlan=vlan, time=epoch)

            tasks = []  # tasks to be launched in thread

            if mac_added:
                tasks.append(functools.partial(DeviceSnmpManager().set_port_of_mac, mac))

            if vlan_added and nac.vlan_has_access_control(vlan):
                tasks.append(functools.partial(self.checkAuthzOnVlan, mac, vlan))

            if tasks:
                task = threading.Thread(target=lambda: [task() for task in tasks])
                task.start()

            source = packet.highest_layer
            # more meaningful name
            if source == 'BROWSER':
                source = 'NetBIOS'
            elif source == 'BOOTP':
                source = 'DHCPV4'

            # Hostname: grab it from netbios or dhcpv4 or dhcpv6 or mdns
            hostname = None
            try:
                hostname = str(packet.nbdgm.source_name)  # ends with <??>
                p = re.compile('<..>$')
                hostname = p.sub('', hostname)
            except AttributeError:
                pass

            try:
                hostname = str(packet.bootp.option_hostname)
            except AttributeError:
                pass

            try:
                hostname = str(packet.dhcpv6.client_fqdn)
            except AttributeError:
                pass

            try:
                if int(packet.mdns.dns_flags_response) and int(packet.mdns.dns_flags_authoritative):
                    mdns = packet.mdns
                    try:
                        a_list = mdns.dns_a.fields.copy()
                        a_list.reverse()
                    except AttributeError:
                        a_list = []
                    try:
                        aaaa_list = mdns.dns_aaaa.fields.copy()
                        aaaa_list.reverse()
                    except AttributeError:
                        aaaa_list = []
                    resp_types = mdns.dns_resp_type.fields.copy()
                    resp_types.reverse()
                    for field in mdns.dns_resp_name.fields:
                        name, *domain = field.showname_value.split('.')
                        if domain == ['local']:
                            resp_type = resp_types.pop().showname_value.split(' ')[0]
                            target = None
                            if resp_type == 'A':
                                target = a_list.pop().showname_value
                            elif resp_type == 'AAAA':
                                target = aaaa_list.pop().showname_value
                            if target:
                                if session.mac_has_ip_on_vlan(mac, target, vlan):
                                    hostname = name
                                    break  # Only first one found...
            except AttributeError:
                pass

            if hostname:
                device.seen_hostname(mac, hostname, source)

            # DHCP fingerprint
            if source == 'DHCPV4':
                try:
                    fingerprint = {
                                'request_list': ','.join(str(option.hex_value) for option in packet.bootp.option_request_list_item.fields),
                                'vendor': str(getattr(packet.bootp, 'option_vendor_class_id', ''))
                    }
                except AttributeError:
                    pass
                else:
                    device.seen_fingerprint(mac, fingerprint, source, hostname)

            elif source == 'DHCPV6':
                try:
                    fingerprint = {
                                'request_list': ','.join(str(option.hex_value) for option in packet.dhcpv6.requested_option_code.fields),
                                'vendor': str(getattr(packet.dhcpv6, 'vendorclass_data', '')),
                                'enterprise': str(getattr(packet.dhcpv6, 'vendorclass_enterprise', ''))
                    }
                except AttributeError:
                    pass
                else:
                    device.seen_fingerprint(mac, fingerprint, source, hostname)

        except Exception:
            ExceptionEvent(source='device-tracker')\
                 .add_data('packet', str(packet))\
                 .notify()

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


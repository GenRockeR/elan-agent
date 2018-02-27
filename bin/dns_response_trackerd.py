#!/usr/bin/env python3

from elan import neuron, utils, rdns
from elan.capture import Capture
from elan.event import ExceptionEvent


class DnsResponseTracker():

    def __init__(self):

        self.synapse = neuron.Synapse()

        self.interfaces = list(utils.physical_ifaces())

    def capture(self):
        capture = Capture(
                name='device-tracker',
                interface=self.interfaces,
                capture_filter='inbound and udp src port 53'
        )

        capture.remove_files()

        for packet in capture:
            self.process_packet(packet)

        raise RuntimeError('Capture Stopped ! if it ever started...')

    def process_packet(self, packet):
        try:
            # device sessions
            mac = packet.eth.dst

            cname_iter = None
            a_iter = None
            aaaa_iter = None

            entries = []
            if hasattr(packet, 'dns'):
                dns = packet.dns
                for name, type_, ttl in zip(dns.resp_name.fields, dns.resp_type.fields, dns.resp_ttl.fields):
                    if type_ == '5':  # CNAME record
                        if cname_iter is None:
                            cname_iter = iter(dns.cname.fields)
                        value = next(cname_iter)
                    elif type_ == '1':  # A record
                        if a_iter is None:
                            a_iter = iter(dns.a.fields)
                        value = next(a_iter)
                    elif type_ == '28':  # AAAA record
                        if aaaa_iter is None:
                            aaaa_iter = iter(dns.aaaa.fields)
                        value = next(aaaa_iter)
                    else:
                        continue

                    entries.append(dict(mac=mac, rdns=name, source=value, ttl=ttl))

                rdns.add_entries(*entries)

        except Exception:
            ExceptionEvent(source='dns-response-tracker')\
                 .add_data('packet', packet)\
                 .notify()


if __name__ == '__main__':
    p = DnsResponseTracker()
    p.capture()


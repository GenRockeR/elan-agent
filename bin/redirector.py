#!/usr/bin/env python3
import datetime
import os
import subprocess

from scapy.all import Ether, sendp

from elan.event import ExceptionEvent
import elan.libnflog_cffi

REDIRECTOR_NFLOG_QUEUE = int(os.environ.get('REDIRECTOR_NFLOG_QUEUE', 20))


class Redirector():
    REDIRECTION_EXPIRY = 60  # seconds

    def __init__(self):
        self.nft_process = self.start_nft_process()
        self.cmd_count = 0

        self.live_redirections = {}

    def start_nft_process(self):
        return subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True)

    def do_redirect(self, src_ip, src_port, dst_ip, dst_port, action, is_retry=False):
        if ':' in src_ip:
            family = 'ip6'
        else:
            family = 'ip'

        if action == 'add':
            cmd = 'add'
            self.live_redirections[(src_ip, src_port, dst_ip, dst_port)] = datetime.datetime.now()
        else:
            if self.live_redirections.pop((src_ip, src_port, dst_ip, dst_port), None):
                cmd = 'delete'
            else:
                cmd = None

        if cmd is not None:
            try:
                print('{cmd} element bridge elan {family}_conn2mark {{ {src_ip} . {src_port} . {dst_ip} . {dst_port} }}'.format(
                                            cmd=cmd,
                                            family=family,
                                            src_ip=src_ip,
                                            src_port=src_port,
                                            dst_ip=dst_ip,
                                            dst_port=dst_port
                        ),
                        file=self.nft_process.stdin,
                        flush=True
                )
            except IOError:
                if is_retry:
                    self.nft_process.terminate(timeout=0)
                    raise
                # try launching again the nft process
                self.restart_nft_process()
                self.do_redirect(src_ip, src_port, dst_ip, dst_port, action, is_retry=True)

            self.cmd_count += 1
            if self.cmd_count > 100:
                self.restart_nft_process()

    def restart_nft_process(self, timeout=3):
        '''
        Soft restart (send quit) of nft process unless timeout=0, then terminate immediately
        After timeout (seconds), terminate process.
        if timeout is None, soft restart with no timeout
        '''
        if timeout == 0:
            self.nft_process.terminate()
        else:
            print('quit', file=self.nft_process.stdin, flush=True)
            try:
                self.nft_process.wait(timeout)
            except subprocess.TimeoutExpired:
                self.nft_process.terminate()
        self.cmd_count = 0
        self.nft_process = self.start_nft_process()

    def do_cleanup(self):
        to_remove = []
        now = datetime.datetime.now()
        for args, setup_time in self.live_redirections.items():
            if setup_time + datetime.timedelta(seconds=self.REDIRECTION_EXPIRY) < now:
                to_remove.append(args)

        for args in to_remove:
            self.do_redirect(*args, action='remove')

    def run(self):
        self.listen_packets()

    def listen_packets(self):
        nflog = elan.libnflog_cffi.NFLOG().generator(REDIRECTOR_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2 ** 24, handle_overflows=False)
        next(nflog)

        for pkt, hwhdr, action in nflog:
            self.process_packet(hwhdr + pkt, action.decode())

    def process_packet(self, packet, action):
        try:
            eth_obj = Ether(packet)
            ip_obj = eth_obj.payload
            tcp_obj = ip_obj.payload

            self.do_redirect(ip_obj.src, tcp_obj.sport, ip_obj.dst, tcp_obj.dport, action)
            self.do_cleanup()

            # TODO : reinject the packet instead of waiting for client retry
            # sendp(eth_obj, iface='injector') does not work: loose vlan info
        except:
            ExceptionEvent(source='network')\
                 .add_data('packet', packet)\
                 .notify()


if __name__ == '__main__':

    redirector = Redirector()
    redirector.run()


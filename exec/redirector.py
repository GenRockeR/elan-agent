#!/usr/bin/env python3
import os
from origin.event import ExceptionEvent
import origin.libnflog_cffi
from scapy.all import Ether
import subprocess

REDIRECTOR_NFLOG_QUEUE = int(os.environ.get('REDIRECTOR_NFLOG_QUEUE', 20))


class Redirector():
    def __init__(self):
        self.nft_process = self.start_nft_process()
    
    def start_nft_process(self):
        return subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True)
    
    def do_redirect(self, src_ip, src_port, dst_ip, dst_port, action, is_retry=False):
        if ':' in src_ip:
            family = 'ip6'
        else:
            family = 'ip'
            
        if action == 'add':
            cmd = 'add'
        else:
            cmd = 'delete'

        try:
            print(  '{cmd} element bridge origin {family}_conn2mark {{ {src_ip} . {src_port} . {dst_ip} . {dst_port} }}'.format(
                                        cmd = cmd,
                                        family = family,
                                        src_ip   = src_ip,
                                        src_port = src_port,
                                        dst_ip   = dst_ip,
                                        dst_port = dst_port
                    ),
                  file=self.nft_process.stdin
            )
        except IOError:
            self.nft_process.terminate()
            if is_retry:
                raise
            # try launching again the nft process
            self.nft_process = self.start_nft_process()
            self.do_redirect(src_ip, src_port, dst_ip, dst_port, action, is_retry=True)
    
    def run(self):
        self.listen_packets()
    
    def listen_packets(self):
        nflog = origin.libnflog_cffi.NFLOG().generator(REDIRECTOR_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2**24, handle_overflows = False)
        next(nflog)
        
        for pkt, hwhdr, action in nflog:
            self.process_packet(hwhdr+pkt, action.decode())
    
    def process_packet(self, packet, action):
        try:
            eth_obj = Ether(packet)
            ip_obj = eth_obj.payload
            tcp_obj = ip_obj.payload
            
            self.do_redirect(ip_obj.src, tcp_obj.sport, ip_obj.dst, tcp_obj.dport, action)
            
            
            # TODO : reinject the packet instead of waiting for client retry
            # TODO : Cleanup maps afet 120 seconds or when in input (nat has be made)
        except:
            ExceptionEvent(source='network')\
                 .add_data('packet', packet)\
                 .notify()

if __name__ == '__main__':

    redirector = Redirector()
    redirector.run()

        
            

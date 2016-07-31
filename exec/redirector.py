#!/usr/bin/env python3
import os
from origin.event import ExceptionEvent
import origin.libnflog_cffi
from scapy.all import Ether
import subprocess

REDIRECTOR_NFLOG_QUEUE = int(os.environ.get('REDIRECTOR_NFLOG_QUEUE', 20))


class Redirector():
    def __init__(self):
        self.nft_process = subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True)
    
    def add_redirect(self, src_ip, src_port, dst_ip, dst_port, mark, is_retry=False):
        if ':' in src_ip:
            family = 'ip6'
        else:
            family = 'ip'

        try:
            print(  'add element {family} origin redirect_marks {{ {src_ip} . {src_port} . {dst_ip} . {dst_port} : {mark} }}'.format(
                                        family = family,
                                        src_ip   = src_ip,
                                        src_port = src_port,
                                        dst_ip   = dst_ip,
                                        dst_port = dst_port,
                                        mark = mark
                    ),
                  file=self.nft_process.stdin
            )
        except IOError:
            self.nft_process.terminate()
            if is_retry:
                raise
            # try launching again the nft process
            self.nft_process = subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True)
            self.add_redirect(src_ip, src_port, dst_ip, dst_port, mark, is_retry=True)
    
    def run(self):
        self.listen_packets()
    
    def listen_packets(self):
        nflog = origin.libnflog_cffi.NFLOG().generator(REDIRECTOR_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'nfmark'], nlbufsiz=2**24, handle_overflows = False)
        next(nflog)
        
        for pkt, hwhdr, nfmark in nflog:
            self.process_packet(hwhdr+pkt, nfmark)
    
    def process_packet(self, packet, mark):
        try:
            eth_obj = Ether(packet)
            ip_obj = eth_obj.payload
            tcp_obj = ip_obj.payload
            
            self.add_redirect(ip_obj.src, tcp_obj.sport, ip_obj.dst, tcp_obj.dport)
            
            
            # TODO : reinject the packet instead of waiting for client retry
            # TODO : Cleanup maps afet 120 seconds or when in input (nat has be made)
        except:
            ExceptionEvent(source='network')\
                 .add_data('packet', packet)\
                 .notify()

if __name__ == '__main__':

    redirector = Redirector()
    redirector.run()

        
            

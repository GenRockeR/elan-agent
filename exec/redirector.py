#!/usr/bin/env python3
import os
from origin.event import ExceptionEvent
import origin.libnflog_cffi
from scapy.all import Ether, sendp
import subprocess
import datetime

REDIRECTOR_NFLOG_QUEUE = int(os.environ.get('REDIRECTOR_NFLOG_QUEUE', 20))


class Redirector():
    REDIRECTION_EXPIRY = 60 #seconds
    def __init__(self):
        self.nft_process = self.start_nft_process()
        
        self.live_redirections = {}
    
    def start_nft_process(self):
        return subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True)
    
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
                print(  '{cmd} element bridge origin {family}_conn2mark {{ {src_ip} . {src_port} . {dst_ip} . {dst_port} }}'.format(
                                            cmd = cmd,
                                            family = family,
                                            src_ip   = src_ip,
                                            src_port = src_port,
                                            dst_ip   = dst_ip,
                                            dst_port = dst_port
                        ),
                        file=self.nft_process.stdin,
                        flush = True
                )
            except IOError:
                self.nft_process.terminate()
                if is_retry:
                    raise
                # try launching again the nft process
                self.nft_process = self.start_nft_process()
                self.do_redirect(src_ip, src_port, dst_ip, dst_port, action, is_retry=True)
    
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

        
            

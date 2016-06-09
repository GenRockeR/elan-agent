#!/usr/bin/env python
import os
from origin.event import ExceptionEvent
from __future__ import print_function
import subprocess

REDIRECTOR_NFLOG_QUEUE = int(os.environ.get('REDIRECTOR_NFLOG_QUEUE', 20))


if __name__ == '__main__':
    import origin.libnflog_cffi
    from origin.neuron import Dendrite
    from impacket.ImpactDecoder import EthDecoder
    from subprocess import call
    
    dendrite = Dendrite('connection-redirector')

    nflog = origin.libnflog_cffi.NFLOG().generator(REDIRECTOR_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'nfmark'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
    nft_process = subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE)
    def nft(cmd):
        print(cmd, file=nft_process.stdin)
    
    for pkt, hwhdr, nfmark in nflog:
        try:
            eth_obj = decoder.decode(pkt)
            ip_obj = eth_obj.child()
            tcp_obj = ip_obj.child()
            
            if ip_obj.__class__.__name__ == 'IP':
                family = 'ip'
                src_ip = ip_obj.get_ip_src()
                dst_ip   = ip_obj.get_ip_dst()
            elif ip_obj.__class__.__name__ == 'IP6':
                family = 'ip6'
                src_ip = ip_obj.get_source_address().as_string()
                dst_ip = ip_obj.get_destination_address().as_string()
            
            nft(    'add element {family} origin redirect_marks {{ {src_ip} . {src_port} . {dst_ip} . {dst_port} : {mark} }}'.format(
                                        family = family,
                                        src_ip   = ip_obj.get_ip_src(),
                                        src_port = tcp_obj.get_th_sport(),
                                        dst_ip   = ip_obj.get_ip_dst(),
                                        dst_port = tcp_obj.get_th_dport(),
                                        mark = nfmark
                    )
            )
            # TODO : reinject the packet instead of waiting for client retry
            # TODO : Cleanup maps afet 120 seconds or when in input (nat has be made)
        
        except IOError:
            nft_process.terminate()
            nft_process = subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True)

        except Exception as e:
            ExceptionEvent(source='network')\
                 .add_data('packet', pkt)\
                 .add_data('hw_header', hwhdr)\
                 .notify()




        
            

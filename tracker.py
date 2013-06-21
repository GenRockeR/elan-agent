#!/usr/bin/env python
from impacket.ImpactDecoder import EthDecoder
import libnflog_cffi

if __name__ == "__main__":
    nflog = libnflog_cffi.NFLOG().generator(0, extra_attrs=['msg_packet_hwhdr'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    decoder = EthDecoder()
    
    for pkt, hwhdr  in nflog:
        try:
            packet = decoder.decode( hwhdr + pkt)
            print(packet)
        except Exception as e:
            # TODO: notify error to central manager...
            print e
            
            

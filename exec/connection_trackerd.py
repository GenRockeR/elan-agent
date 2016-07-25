#!/usr/bin/env python
import os
from origin.event import ExceptionEvent, InternalEvent
from origin import session, neuron
import pyshark
import time
import struct
from origin.utils  import if_indextoname


CONNECTION_NFLOG_QUEUE = int(os.environ.get('CONNECTION_NFLOG_QUEUE', 5))

def ignorePacket(pkt):
    macs2ignore = ('ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00')
    
    for t in ('src', 'dst'):
        # Ignore broadcast packets
        if pkt[t]['mac'] in macs2ignore:
            return True
    
        # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
        # name is IANA_{integer}, integer being the number of prefixed bytes.
        IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
        if pkt[t]['mac'][0:8] in IANA_6_prefix:
            return True
        IANA_4_prefix = ['33:33']
        if pkt[t]['mac'][0:5] in IANA_4_prefix:
            return True

    return False


class ConnectionTracker():
    def __init__(self, dendrite=None):
        if dendrite is None:
            dendrite = neuron.Dendrite()
        self.dendrite = dendrite
        
    def capture(self):
        for packet in pyshark.LiveCapture(
                                            interface=['nflog:'+str(CONNECTION_NFLOG_QUEUE)],
                                         ).sniff_continuously():
            self.process_packet(packet)
            
        raise RuntimeError('Capture Stopped ! if it ever started...')

    def process_packet(self, packet):
        try:
            ip = packet.layers[1]
            pkt_params = {
                    'src': { 'ip': ip.src }, 
                    'dst': { 'ip': ip.dst },
            }
            # TODO: Better way to find macs from nflog layer... 
            for tlv in packet.nflog.tlv.alternate_fields:
                if tlv.showname_value.startswith('NFULA_HWHEADER'):
                    pkt_params['src']['mac']= tlv.show[30:47]
                    pkt_params['dst']['mac']= tlv.show[12:29]
                    break
                
            if not ignorePacket(pkt_params):
                pkt_params['start'] = time.strftime( '%Y-%m-%dT%H:%M:%SZ', time.gmtime(float(packet.frame_info.time_epoch)) )
 
                if packet.transport_layer:
                    pkt_params['transport'] = packet.transport_layer.lower()

                for layer in reversed(packet.layers):
                    if layer.layer_name != 'data':
                        pkt_params['protocol'] = layer.layer_name
                        break
                
                if len(packet.layers) > 2 and getattr(packet.layers[2], 'srcport', None) is not None:
                    pkt_params['src']['port']= packet.layers[2].srcport
                    pkt_params['dst']['port']= packet.layers[2].dstport
                

                    
                for tlv in packet.nflog.tlv.alternate_fields:
                    if tlv.showname_value.startswith('NFULA_IFINDEX_PHYSINDEV'):
                        physindev = struct.unpack(">L", tlv.binary_value[-4:])[0]
                        pkt_params['src']['vlan'] = if_indextoname(physindev)
                        if pkt_params['src']['vlan'] and '.' not in pkt_params['src']['vlan']:
                            pkt_params['src']['vlan'] += '.0'
                            
                    if tlv.showname_value.startswith('NFULA_IFINDEX_PHYSOUTDEV'):
                        physoutdev =  struct.unpack(">L", tlv.binary_value[-4:])[0]
                        pkt_params['dst']['vlan']   = if_indextoname(physoutdev)
                        if pkt_params['dst']['vlan'] and '.' not in pkt_params['dst']['vlan']:
                            pkt_params['dst']['vlan'] += '.0'
                            
                for t in ('src', 'dst'):
                    tip = pkt_params[t]
                    if 'ip' in tip:
                        tip['is_mac_ip'] = session.mac_has_ip_on_vlan(tip['mac'], tip['ip'], tip['vlan'])
                    else:
                        tip['is_mac_ip'] = False
                
                self.dendrite.publish('connection', pkt_params)

        except Exception as e:
            ExceptionEvent(source='network')\
                 .add_data('packet', packet)\
                 .notify()
     

if __name__ == '__main__':
    ct = ConnectionTracker()
    ct.capture()


        
            

#!/usr/bin/env python
import os

DHCP_NFLOG_QUEUE = int(os.environ.get('DHCP_NFLOG_QUEUE', 15))

from pydhcplib.dhcp_packet import DhcpPacket
import struct
from origin.neuron import Synapse

def getData(pkt_obj):
    if pkt_obj.__class__.__name__ == 'Data':
        return pkt_obj
    if pkt_obj.child():
        return getData(pkt_obj.child())
    return None

def getDhcpOptions(dhcp_data_obj):
    '''
    Compute DHCP fingerprint from Impacket Data object and retrieve useful options
    Returns None if not  dhcp packet 
    Returns empty dict {} if dhcp packet with no useful information for us
    Returns dict { 'mac':..., 'fingerprint':..., 'hostname':..., extraparam1:..., extraparam2:... } 
      if fingerprintable (ie must be DHCP packet  with parameter request list), includes fingerprint
      hostname returned if present
      extraparam are params used by fingerbank. up to now only vendor_id

    Note: Strings (hostname, vendor_id) are considered ASCII strings, no UTF8
    '''
    dhcp = DhcpPacket()
    dhcp.DecodePacket( dhcp_data_obj.get_buffer_as_string() )
    if not dhcp.IsDhcpPacket():
        return None

    options = {}
    
    # Parameter Request List
    prl = dhcp.GetOption('parameter_request_list')
    if prl:
        # FingerPrint is a string of comma separated option numbers (with no spaces)
        options = { 'fingerprint': str(prl).replace(' ', '').replace('[', '').replace(']', '') }
        vendor_id = dhcp.GetOption('vendor_class')
        if vendor_id:
            options['vendor_id'] = struct.pack('B' * len(vendor_id), *vendor_id )
    
    hostname = dhcp.GetOption('host_name')
    if hostname:
        options['hostname'] = struct.pack('B' * len(hostname), *hostname )

    if prl or hostname:
        hwaddr = dhcp.GetHardwareAddress()
        options['mac'] = ('{:0=2x}:'*5+'{:0=2x}').format( *hwaddr )

    return options

class TrackedDHCPOptions():
    REDIS_LIFETIME = 60 * 24 * 60 * 60 # 60 days in seconds
    synapse = Synapse()
    
    @classmethod
    def isNewFingerprint(cls, mac, options):
        key = 'dhcp:fingerprint:{mac}'.format(mac=mac)
        if cls.synapse.get(key) == options:
            cls.synapse.expire(key, cls.REDIS_LIFETIME)
            return False
        else:
            cls.synapse.set(key, options, ex=cls.REDIS_LIFETIME)
            return True
        
    @classmethod
    def isNewHostname(cls, mac, hostname):
        key = 'dhcp:hostname:{mac}'.format(mac=mac)
        if cls.synapse.get(key) == hostname:
            cls.synapse.expire(key, cls.REDIS_LIFETIME)
            return False
        else:
            cls.synapse.set(key, hostname, ex=cls.REDIS_LIFETIME)
            return True


if __name__ == '__main__':
    import origin.libnflog_cffi
    import signal
    from origin.neuron import Dendrite
    from impacket.ImpactDecoder import EthDecoder
    
    dendrite = Dendrite('dhcp-tracker')

    nflog = origin.libnflog_cffi.NFLOG().generator(DHCP_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
     
    fingerprints = {}
    hostnames = {}
    for pkt, hwhdr, direction  in nflog:
        try:
            pkt_obj = decoder.decode(hwhdr + pkt)
            pkt_data_obj = getData(pkt_obj)
            options = getDhcpOptions(pkt_data_obj)

            mac = options.get('mac')
            hostname = options.get('hostname', None)
            if hostname:
                if TrackedDHCPOptions.isNewHostname(mac, hostname):
                    dendrite.post('device/dhcp-name', {'mac': mac, 'name': hostname})
                del options['hostname'] # delete it so it does not get posted with fingerprint

            if 'fingerprint' in options and TrackedDHCPOptions.isNewFingerprint(mac, options):
                dendrite.post('device/dhcp-fingerprint', options)

        except Exception as e:
            # TODO: notify error to central manager...
            print 'Exception: ', type(e), e



        
            

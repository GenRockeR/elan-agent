#!/usr/bin/env python

DHCP_NFLOG_QUEUE = 5

from pydhcplib.dhcp_packet import DhcpPacket
import struct

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

def isNewFingerprint(fps, opts):
    mac = opts['mac']
    if (mac in fps and fps[mac] != opts) or (mac not in fps):
        fps[mac] = opts
        return True
    return False

def isNewHostname(hostnames, opts):
    mac = opts['mac']
    if (mac in hostnames and hostnames[mac] != opts['hostname']) or (mac not in hostnames):
        hostnames[mac] = opts['hostname']
        return True
    return False


if __name__ == '__main__':
    import origin.libnflog_cffi
    import signal
    from origin.synapse import Synapse
    from impacket.ImpactDecoder import EthDecoder
    
    fingerprints = {}
    post_pool = ()
        
    fp_synapse = Synapse(path = 'device/dhcp-fingerprint')
    hn_synapse = Synapse(path = 'device/dhcp-name')

    nflog = origin.libnflog_cffi.NFLOG().generator(DHCP_NFLOG_QUEUE, extra_attrs=['msg_packet_hwhdr', 'prefix'], nlbufsiz=2**24, handle_overflows = False)
    fd = next(nflog)
    
    decoder = EthDecoder()
    
     
    # catch TERM signal so final post can execute.
    def noop(signum, frame):
        pass
    signal.signal(signal.SIGTERM, noop)
    
    
    try:
        fingerprints = {}
        hostnames = {}
        for pkt, hwhdr, direction  in nflog:
            try:
                pkt_obj = decoder.decode(hwhdr + pkt)
                pkt_data_obj = getData(pkt_obj)
                options = getDhcpOptions(pkt_data_obj)

                if 'hostname' in options:
                    if isNewHostname(hostnames, options):
                        hn_synapse.postPoolAdd({'mac': options['mac'], 'name': options['hostname']})
                    del options['hostname'] # delete it so it does not get posted with fingerprint
                hn_synapse.submitPostPoolIfReady()

                if 'fingerprint' in options and isNewFingerprint(fingerprints, options):
                    fp_synapse.postPoolAdd(options)
                fp_synapse.submitPostPoolIfReady()

            except Exception as e:
                # TODO: notify error to central manager...
                print 'Exception: ', type(e), e
    finally:
        fp_synapse.flushPostPool()



        
            

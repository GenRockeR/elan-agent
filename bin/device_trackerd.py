#!/usr/bin/env python3

from origin import session, nac, neuron
from origin.event import Event, ExceptionEvent
import os
import time
from wirepy.lib import column, dfilter, dumpcap, epan, wtap, prefs
import threading

REDIS_LIFETIME = 60 * 24 * 60 * 60 # 60 days in seconds

# Some required setup
epan.epan_init()
prefs.read_prefs()
epan.cleanup_dissection()
epan.init_dissection()

dendrite = neuron.Dendrite('device-tracker')



def isNewFingerprint(mac, fingerprint, source):
    key = 'mac:{mac}:fingerprint:{source}'.format(mac=mac, source=source)
    if dendrite.synapse.get(key) == fingerprint:
        dendrite.synapse.expire(key, REDIS_LIFETIME)
        return False
    else:
        dendrite.synapse.set(key, fingerprint, ex=REDIS_LIFETIME)
        return True

def isNewHostname(mac, hostname, source):
    key = 'mac:{mac}:hostname:{source}'.format(source=source, mac=mac)
    if dendrite.synapse.get(key) == hostname:
        dendrite.synapse.expire(key, REDIS_LIFETIME)
        return False
    else:
        dendrite.synapse.set(key, hostname, ex=REDIS_LIFETIME)
        return True

def ignoreMAC(mac):
    # Ignore broadcast packets
    if mac in ['ff:ff:ff:ff:ff:ff', '00:00:00:00:00:00']:
        return True

    # Ignore IANA Reserved MACs: http://www.iana.org/assignments/ethernet-numbers/ethernet-numbers.xml
    # name is IANA_{integer}, integer being the number of prefixed bytes.
    IANA_6_prefix = ['00:00:5e', '01:00:5e', '02:00:5e', '03:00:5e']
    if mac[0:8] in IANA_6_prefix:
        return True
    IANA_4_prefix = ['33:33']
    if mac[0:5] in IANA_4_prefix:
        return True

    return False

def ignoreIP(ip):
    # Ignore broadcast
    if ip[:6] == '0.0.0.' or ip in ('255.255.255.255', '::'):
        return True
    #Ignore multicast
    if ip[:4] in [str(v)+'.' for v in range(224,239)]: # 224. to 239.
        return True
    
    if ip == '::':
        return True
    
    return False

def checkAuthzOnVlan(mac, vlan):
    authz = nac.checkAuthz(mac)
    if not authz or authz.vlan != vlan:
        event = Event('device-not-authorized', source='network', level='danger') 
        event.add_data('mac',  mac, data_type='mac')
        event.add_data('vlan', vlan)
        event.notify()
        # TODO: Try to move it to another vlan!

# Some general information we are interested in for every packet
CINFO = column.ColumnInfo([
        #column.Format(column.Type.INFO,           title='info'),
        column.Format(column.Type.PROTOCOL,       title='protocol'),
        column.Format(column.Type.CUSTOM,         title='interface-id',     custom_field='frame.interface_id'),
        column.Format(column.Type.CUSTOM,         title='time',             custom_field='frame.time_epoch'),
        column.Format(column.Type.UNRES_DL_SRC,   title='src-mac'),
        #column.Format(column.Type.UNRES_DL_DST,   title='dst-mac'),
        column.Format(column.Type.UNRES_NET_SRC,  title='src-ip'),
        #column.Format(column.Type.UNRES_NET_DST,  title='dst-ip'),
        #column.Format(column.Type.UNRES_SRC_PORT, title='src-port'),
        #column.Format(column.Type.UNRES_DST_PORT, title='dst-port'),
        column.Format(column.Type.CUSTOM,         title='vlan-id',          custom_field='vlan.id'),
        column.Format(column.Type.CUSTOM,         title='src-ip',           custom_field='arp.src.proto_ipv4'),
        #column.Format(column.Type.CUSTOM,         title='dst-ip',           custom_field='arp.dst.proto_ipv4'),
        column.Format(column.Type.CUSTOM,         title='icmpv6-type',      custom_field='icmpv6.type'),
        column.Format(column.Type.CUSTOM,         title='hostname',         custom_field='dhcpv6.domain'),
        column.Format(column.Type.CUSTOM,         title='hostname',         custom_field='bootp.option.hostname'),
        column.Format(column.Type.CUSTOM,         title='dhcp-request-list',custom_field='bootp.option.request_list_item'),
        column.Format(column.Type.CUSTOM,         title='dhcp-vendor-id',   custom_field='bootp.option.vendor_class_id'),
        column.Format(column.Type.CUSTOM,         title='browser-command',  custom_field='browser.command'),
        column.Format(column.Type.CUSTOM,         title='hostname',         custom_field='browser.server'),
])

def process_frame(wt, frame):
    # Dissect a single frame using the wtap's current state
    edt = epan.Dissect()

    edt.prime_cinfo(CINFO)
    edt.run(wt, frame, CINFO)
    #if not FILTER_HTTP.apply_edt(edt):
        # No http traffic in the packet, throw it away
    #    return
    edt.fill_in_columns()
    #_display_tree_fi(edt.tree)
    fields = {
                CINFO.titles[i]: epan.iface.string(CINFO._col_datap[i]) 
                    for i in range(len(CINFO))
                        if epan.iface.string(CINFO._col_datap[i])
             }

    if ignoreMAC(fields['src-mac']):
        return

    mac = fields['src-mac']
    vlan = fields.get('vlan-id', 0)
    epoch = int(float(fields['time']))
    
    if(   (  fields['protocol'] == 'ARP' 
             or 
             fields['protocol'] == 'ICMPv6' and fields['icmpv6-type'] in ('Neighbor Advertisement', 'Neighbor Solicitation')
          ) 
          and not ignoreIP(fields['src-ip'])    ):
        mac_added, vlan_added, ip_added = session.seen(mac, vlan=vlan , ip=fields['src-ip'], time=epoch)
    else:
        mac_added, vlan_added, ip_added = session.seen(mac, vlan=vlan , time=epoch)

    if vlan_added:
        # Check Mac authorized on VLAN
        thread = threading.Thread(target=checkAuthzOnVlan, args=(mac, vlan))
        thread.start()

    source = fields['protocol']
    if source == 'BROWSER':
        source = 'NetBIOS'
    
    if 'hostname' in fields:
        hostname = fields['hostname']
        
        if source != 'NetBIOS' or fields['browser-command'] in ('Host Announcement', 'Local Master Announcement'):
            if isNewHostname(mac, hostname, source):
                dendrite.post('mac/{mac}/hostname'.format(mac=mac), {'name': hostname, 'source': source})

    if('dhcp-request-list' in fields):
        fingerprint = { 'fingerprint': fields['dhcp-request-list'], 'vendor_id': fields.get('vendor_id', '') }
        if isNewFingerprint(mac, fingerprint, source=source):
            dendrite.post('mac/{mac}/fingerprint'.format(mac=mac, source=source), dict(source=source, **fingerprint))
  
def iter_frames():
    with dumpcap.CaptureSession(    interfaces=('eth0', 'eth1' ),
                                    capture_filter='inbound', 
                                    #capture_filter='inbound and ( udp port 67 or arp or udp port 138 or udp port 547 or (icmp6 and ip6[40] == 0x88) )',
                                    ringbuffer_filesize=10240, savefile='/tmp/device_tracker_dump'
                               ) as cap:
        try:
            event_type, event_msg = cap.wait_for_event()
            while event_type != cap.SP_FILE:
                print('Unexpected event from dumpcap', event_msg)
                event_type, event_msg = cap.wait_for_event()
        except dumpcap.NoEvents:
            # Child did not start capturing...
            errmsg = ('Dumpcap did not start receiving packets for some time.'
                      ' Giving up.')
            raise RuntimeError(errmsg)
        # Received the first file dumpcap is writing to. Since we didnt request
        # a ringbuffer, dumpcap will write to only one file for the entire
        # session.
        fname = event_msg
        while True:
            with wtap.WTAP.open_offline(fname) as wt:
                os.remove(fname) # unlink file now it is opened
                
                frameiter = iter(wt)
                # Started to read from the current savefile. Now wait for
                # dumpcap to report about written packets.
                for event_type, event_msg in iter(cap):
                    if event_type == cap.SP_PACKET_COUNT:
                        # Dissect as many packets as have been written
                        for i in range(event_msg):
                            wt.clear_eof()
                            try:
                                frame = next(frameiter)
                            except StopIteration:
                                errmsg = ('Dumpcap reported new packets, but the capture-file does not have them.')
                                raise RuntimeError
                            yield wt, frame
                    elif event_type == cap.SP_FILE:
                        # A new savefile has been created, stop reading from
                        # the current file.
                        fname = event_msg
                        break
                else:
                    # The iterator on cap reaches this point if there are
                    # no more events from dumpcap - capturing has stopped,
                    # quit the loop
                    break



if __name__ == '__main__':
    for i in range(1, 100):
        try:
            for wt, frame in iter_frames():
                process_frame(wt, frame)
        except:
            ExceptionEvent(source='network').notify()
            time.sleep(1)


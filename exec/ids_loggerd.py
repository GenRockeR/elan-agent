#!/usr/bin/env python3

import asyncio
import subprocess
from idstools import unified2
from scapy.all import Ether
from origin.neuron import Dendrite
from origin.event import Event, ExceptionEvent


async def get_bridge_port(mac):
    # TODO: find a better way to get port
    process = await asyncio.create_subprocess_shell("bridge fdb | grep  '{mac}' | grep -v permanent | cut -f3 -d' '".format(mac=mac), stdout=subprocess.PIPE)
    response = await process.communicate()
    return response[0].decode().split('\n', 1)[0]


class IdsLogger():
    DEFAULT_DIRECTORY = '/var/log/suricata'
    DEFAULT_PREFIX = 'unified2.alert'
    
    def __init__(self, dendrite=None, directory=DEFAULT_DIRECTORY, prefix=DEFAULT_PREFIX, delete_files=True, loop=None):
        if dendrite is None:
            dendrite = Dendrite()
        if loop is None:
            loop = asyncio.get_event_loop()
            
        self.dendrite = dendrite
        self.directory = directory
        self.prefix = prefix
        self.delete_files = delete_files
        self.loop = loop
        
    def run(self):
        self.loop.run_until_complete( self.loop.run_in_executor(None, self.read_ids_events) )

    def read_ids_events(self):
        reader = unified2.SpoolEventReader(
                self.directory, 
                self.prefix,
                follow=True,
                bookmark=True,
                delete=self.delete_files)
    
    
        for alert in reader:
            asyncio.run_coroutine_threadsafe(self.process_alert(alert), loop=self.loop)

    async def process_alert(self, alert):
        try: 
            #timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.'+ str(event['event-microsecond']) +'Z', time.gmtime(event['event-second']))
            event = Event(event_type='device-alert', source='ids', level='danger', timestamp=alert['event-second'], dendrite=self.dendrite)
            event.add_data('priority', alert['priority'])
            event.add_data('signature', alert['signature-id'], data_type = 'signature')
            event.add_data('revision', alert['signature-revision'])
        
            # decode Ethernet packet to get mac addresses and protocol
            # TODO: This may be nflog wrapped now it is sent via nflog? to be checked...
            packet = b''
            for p in alert['packets']:
                packet += p
            packet = Ether( packet )
            
            src_mac = packet.src
            if src_mac != '00:00:00:00:00:00':    
                event.add_data( 'src_mac', src_mac, 'mac' )
                        
            dst_mac = packet.dst
            if dst_mac != '00:00:00:00:00:00':    
                event.add_data( 'dst_mac', dst_mac, 'mac' )
                    
            src_vlan = get_bridge_port(src_mac)
            if src_vlan:
                event.add_data( 'src_vlan', src_vlan )
        
            dst_vlan = get_bridge_port(dst_mac)
            if dst_vlan:
                event.add_data( 'dst_vlan', dst_vlan )
        
            protocol = None
            while packet:
                if packet.name not in ( 'Raw', 'Padding' ):
                    protocol = packet.name
                packet = packet.payload
        
            if protocol:
                event.add_data( 'protocol', protocol )
                
        
            event.add_data( 'src_ip',   alert['source-ip'] )
            event.add_data( 'dst_ip',   alert['destination-ip'] )
            event.add_data( 'src_port', alert['sport-itype'] )
            event.add_data( 'dst_port', alert['dport-icode'] )
        
            event.notify()
        except:
            ExceptionEvent(source='ids').notify()


if __name__ == "__main__":
    idsLogger = IdsLogger()
    idsLogger.run()

    
    

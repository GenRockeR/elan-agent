#!/usr/bin/env python3

import subprocess, traceback
from origin.neuron import Dendrite, Synapse, RequestTimeout
from origin.utils import reload_service, physical_ifaces
from origin import network
from origin.event import ExceptionEvent
from mako.template import Template
from pyroute2 import IPDB
from origin import nac

class AccessControlConfigurator():
    bridge = 'br0'
    
    def __init__(self):
        
        self.agent_path = None
        self.vlans_path = None
        
        self.vlans = {} # vlans by Vlan-ID
        
    def new_vlan_conf(self, conf):
        # conf is list of all VLANS -> when a Vlan is modified, all VLANs are sent
        new_vlans = {}
        for vlan in conf:
            if vlan.get('vlan_id', 0):
                nic_name = '{nic}.{vid}'.format(nic=vlan['interface'], vid=vlan['vlan_id'])
            else:
                nic_name = vlan['interface']
            new_vlans[ nic_name ] = vlan
        
        self.apply_new_vlan_conf(new_vlans)
    
    def apply_new_vlan_conf(self, new_vlans):
        # New VLANS
        ip = IPDB(mode='direct')
        try:
            bridge = ip.interfaces[self.bridge]
            
            # Create New VLANs
            for nic_name in set(new_vlans.keys()) - set(self.vlans.keys()):
                try:
                    nic = ip.interfaces[ new_vlans[nic_name]['interface'] ]
                    vlan_id = new_vlans[nic_name].get('vlan_id', 0)
                    # Make sure NIC is up
                    nic.up()
                    
                    if vlan_id:
                        nic = ip.create(kind='vlan',link=nic, vlan_id=vlan_id, ifname=nic_name, reuse=True).commit()
                        nic.up()
                    
                    bridge.add_port(nic)
                except:
                    ExceptionEvent(source='network').notify()


            
            # Configure VLANs
            # TODO: use nft from pyroute2 when ready
            with subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True, stdout=subprocess.DEVNULL) as nft_process:
                def nft(*cmds):
                    print(*cmds, file=nft_process.stdin)
                        
                for nic_name, new_vlan in new_vlans.items():
                    # configure Access Contol
                    if new_vlan.get('access_control', False):
                        nft('add element bridge origin ac_ifs {{{nic}}}'.format(nic=nic_name))
                        local_index = self.get_vlan_local_index(nic_name)
                        new_vlan['local_index'] = local_index
                        mark = local_index
                        nft('add element bridge origin vlan_mark {{ {nic} : {mark} }}'.format(nic=nic_name, mark = mark))
        
                        # configure captive portal if access control is enabled
                        new_vlan['http_port'] = 20000 + local_index * 2
                        new_vlan['https_port'] = 20000 + local_index * 2 + 1
                        for protocol in ['ip', 'ip6']:
                            if new_vlan['web_authentication'] or new_vlan['guest_access']:
                                nft("add element {protocol} origin captive_portals {{ {mark} . 80: {http_port} , {mark} . 443: {https_port} }}".format(protocol = protocol, mark = mark, http_port = new_vlan['http_port'], https_port = new_vlan['https_port']))
                            else:
                                nft("delete element {protocol} origin captive_portals {{ {mark} . 80, {mark} . 443 }}".format(protocol = protocol, mark = mark))
        
                        # configure DHCP passthrough
                        if new_vlan['dhcp_passthrough_bridge']:
                            nic_out = new_vlan['dhcp_passthrough_interface']
                            if new_vlan['dhcp_passthrough_vlan_id']:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=new_vlan['dhcp_passthrough_vlan_id'])
                            new_vlan['dhcp_passthrough_ifname'] = nic_out
                            nft('add element bridge origin dhcp_pt_ifs {{ {nic_in} . {nic_out} }}'.format(nic_in=nic_name, nic_out=nic_out))
                        elif nic_name in self.vlans and 'dhcp_passthrough_ifname' in self.vlans[nic_name] and self.vlans[nic_name]['dhcp_passthrough_ifname']:
                            nft('delete element bridge origin dhcp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=self.vlans[nic_name]['dhcp_passthrough_ifname']))
                            
                        # configure DNS passthrough
                        if new_vlan['dns_passthrough_bridge']:
                            nic_out = new_vlan['dns_passthrough_interface']
                            if new_vlan['dns_passthrough_vlan_id']:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=new_vlan['dns_passthrough_vlan_id'])
                            new_vlan['dns_passthrough_ifname'] = nic_out
                            nft('add element bridge origin dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))
                        elif nic_name in self.vlans and 'dns_passthrough_ifname' in self.vlans[nic_name] and self.vlans[nic_name]['dns_passthrough_ifname']:
                            nft('delete element bridge origin dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=self.vlans[nic_name]['dns_passthrough_ifname']))
    
                        if new_vlan['log']:
                            nft('add element bridge origin log_ifs {{ {nic} }}'.format(nic=nic_name))
                        else:
                            nft('delete element bridge origin log_ifs {{ {nic} }}'.format(nic=nic_name))
        
                        if new_vlan['ids']:
                            nft('add element bridge origin ids_ifs {{ {nic} }}'.format(nic=nic_name))
                        else:
                            nft('delete element bridge origin ids_ifs {{ {nic} }}'.format(nic=nic_name))
    
                    else:
                        nft('delete element bridge origin ac_ifs {{{nic}}}'.format(nic=nic_name))
                
            # VLANs to delete
            for nic_name in set(self.vlans.keys()) - set(new_vlans.keys()):
                old_vlan = self.vlans[nic_name]
                vlan_id  = old_vlan['vlan_id']
                
                # TODO: use nft from pyroute2 when ready
                with subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True, stdout=subprocess.DEVNULL) as nft_process:
                    def nft(*cmds):
                        print(*cmds, file=nft_process.stdin)
                            
                    if old_vlan['dhcp_passthrough_bridge']:
                        nft('delete element bridge origin dhcp_pt_ifs {{ {nic_in} . {nic_out} }}'.format(nic_in=nic_name, nic_out=old_vlan['dhcp_passthrough_ifname']))
                    
                    if old_vlan['dns_passthrough_bridge']:
                        nft('delete element bridge origin dns_pt_ifs {{ {nic_in} . {nic_out} }}'.format(nic_in=nic_name, nic_out=old_vlan['dns_passthrough_ifname']))
    
                    for protocol in ['ip', 'ip6']:
                        nft("delete element {protocol} origin captive_portals {{ {mark} . 80, {mark} . 443 }}".format(protocol = protocol, mark = old_vlan['local_index']))
                
                try:
                    nic = ip.interfaces[nic_name]
                    if vlan_id:
                        nic.remove()
                    else:
                        bridge.del_port(nic)
                except:
                    #TODO log error to CC
                    print('error occured:', traceback.format_exc() )

                
            # Set captive portals
            nginx_captive_portals = Template(filename = '/origin/network/nginx/server')
            with open("/etc/nginx/sites-enabled/captive-portal", "w") as nginx_file:
                nginx_file.write(nginx_captive_portals.render(vlans=new_vlans))

            reload_service('nginx')
            
            self.vlans = new_vlans

            nac.set_access_controlled_vlans_cache(new_vlans.keys())
            
        finally:
            ip.release()
            network.NetworkConfiguration.reload()            


    def get_vlan_local_index(self, nic):
        VLAN_LOCAL_INDEX_PATH = 'conf:local_index:by_ifname'
        VLAN_LOCAL_INDEX_INDEX_PATH = 'conf:local_index:index'
        synapse = Synapse()
        index = synapse.hget(VLAN_LOCAL_INDEX_PATH, nic)
        if not index:
            # create an index for that vlan
            def safe_index(pipe):
                if not synapse.hget(VLAN_LOCAL_INDEX_PATH, nic):
                    index = pipe.get(VLAN_LOCAL_INDEX_INDEX_PATH) or 0
                    pipe.multi()
                    index += 1
                    pipe.set(VLAN_LOCAL_INDEX_INDEX_PATH, index)
                    pipe.hset(VLAN_LOCAL_INDEX_PATH, nic, index)
            
            synapse.transaction(safe_index, VLAN_LOCAL_INDEX_INDEX_PATH)
            index = synapse.hget(VLAN_LOCAL_INDEX_PATH, nic)
        return index

if __name__ == "__main__":
    configurator = AccessControlConfigurator()

    dendrite = Dendrite()

    # Set default conf if not yet configured  
    try:
        vlans = dendrite.get_conf('vlans', timeout=5)
    except RequestTimeout:
        # Default vlan conf: first 2 interfaces bridged
        vlans = []
        count = 0
        for interface in physical_ifaces():
            count += 1
            vlans.append({'interface': interface})
            if count == 2:
                break
    configurator.new_vlan_conf(vlans)
    
    dendrite.subscribe_conf('vlans', cb=configurator.new_vlan_conf)

    # wait for changes
    dendrite.wait_complete()

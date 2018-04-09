#!/usr/bin/env python3

from mako.template import Template
from pyroute2 import IPDB
import subprocess, traceback

from elan import nac, network
from elan.event import ExceptionEvent
from elan.neuron import Dendrite, Synapse, RequestTimeout
from elan.utils import reload_service, physical_ifaces


class AccessControlConfigurator():
    bridge = 'br0'

    def __init__(self):

        self.agent_path = None
        self.vlans_path = None

        self.vlans_by_ifname = {}  # vlans by NIC name (<nic>.<vlan>)
        self.vlans_by_id = {}  # vlans by Vlan-ID

    def new_vlan_conf(self, conf):
        # conf is list of all VLANS -> when a Vlan is modified, all VLANs are sent
        new_vlans_by_ifname = {}
        new_vlans_by_id = {}
        for vlan in conf:
            new_vlans_by_id[vlan['id']] = vlan
            if vlan.get('vlan_id', 0):
                nic_name = '{nic}.{vid}'.format(nic=vlan['interface'], vid=vlan['vlan_id'])
            else:
                nic_name = vlan['interface']
            new_vlans_by_ifname[ nic_name ] = vlan

        ip = IPDB(mode='direct')
        try:
            bridge = ip.interfaces[self.bridge]

            # Create New VLANs
            for nic_name in set(new_vlans_by_ifname.keys()) - set(self.vlans_by_ifname.keys()):
                try:
                    nic = ip.interfaces[ new_vlans_by_ifname[nic_name]['interface'] ]
                    vlan_id = new_vlans_by_ifname[nic_name].get('vlan_id', 0)
                    # Make sure NIC is up
                    nic.up()

                    if vlan_id:
                        nic = ip.create(kind='vlan', link=nic, vlan_id=vlan_id, ifname=nic_name, reuse=True).commit()
                        nic.up()

                    bridge.add_port(nic)
                except:
                    ExceptionEvent(source='network').notify()

            # Configure VLANs
            # TODO: use nft from pyroute2 when ready
            with subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True, stdout=subprocess.DEVNULL) as nft_process:

                def nft(*cmds):
                    print(*cmds, file=nft_process.stdin, flush=True)

                for nic_name, new_vlan in new_vlans_by_ifname.items():
                    # configure Access Contol
                    if new_vlan.get('access_control', False):
                        nft('add element bridge elan ac_ifs {{{nic}}}'.format(nic=nic_name))
                    else:
                        nft('delete element bridge elan ac_ifs {{{nic}}}'.format(nic=nic_name))

                    local_index = self.get_vlan_local_index(nic_name)
                    new_vlan['local_index'] = local_index
                    mark = local_index
                    nft('add element bridge elan vlan_mark {{ {nic} : {mark} }}'.format(nic=nic_name, mark=mark))

                    # configure captive portal
                    new_vlan['http_port'] = 20000 + local_index * 2
                    new_vlan['https_port'] = 20000 + local_index * 2 + 1
                    for protocol in ['ip', 'ip6']:
                        nft("add element {protocol} elan captive_portals {{ {mark} . 80: {http_port} , {mark} . 443: {https_port} }}".format(protocol=protocol, mark=mark, http_port=new_vlan['http_port'], https_port=new_vlan['https_port']))

                    # configure DHCP passthrough
                    for pt in new_vlan.get('dhcp_passthroughs', []):
                        if pt not in self.vlans_by_ifname.get(nic_name, {}).get('dhcp_passthroughs', []):
                            # add non existing passthrough
                            nic_out = new_vlans_by_id[pt]['interface']
                            vlan_id = new_vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('add element bridge elan dhcp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))
                    for pt in self.vlans_by_ifname.get(nic_name, {}).get('dhcp_passthroughs', []):
                        if pt not in new_vlan.get('dhcp_passthroughs', []):
                            # delete no longer existing passthrough
                            nic_out = self.vlans_by_id[pt]['interface']
                            vlan_id = self.vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('delete element bridge elan dhcp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    # configure DNS passthrough
                    for pt in new_vlan.get('dns_passthroughs', []):
                        if pt not in self.vlans_by_ifname.get(nic_name, {}).get('dns_passthroughs', []):
                            # add non existing passthrough
                            nic_out = new_vlans_by_id[pt]['interface']
                            vlan_id = new_vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('add element bridge elan dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))
                    for pt in self.vlans_by_ifname.get(nic_name, {}).get('dns_passthroughs', []):
                        if pt not in new_vlan.get('dns_passthroughs', []):
                            # delete no longer existing passthrough
                            nic_out = self.vlans_by_id[pt]['interface']
                            vlan_id = self.vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('delete element bridge elan dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    # configure ARP/NDP passthrough
                    for pt in new_vlan.get('ndp_passthroughs', []):
                        if pt not in self.vlans_by_ifname.get(nic_name, {}).get('ndp_passthroughs', []):
                            # add non existing passthrough
                            nic_out = new_vlans_by_id[pt]['interface']
                            vlan_id = new_vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('add element bridge elan ndp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))
                    for pt in self.vlans_by_ifname.get(nic_name, {}).get('ndp_passthroughs', []):
                        if pt not in new_vlan.get('ndp_passthroughs', []):
                            # delete no longer existing passthrough
                            nic_out = self.vlans_by_id[pt]['interface']
                            vlan_id = self.vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('delete element bridge elan ndp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    # configure mDNS passthroughs
                    for pt in new_vlan.get('mdns_answers_passthroughs', []):
                        if pt not in self.vlans_by_ifname.get(nic_name, {}).get('mdns_answers_passthroughs', []):
                            # add non existing passthrough
                            nic_out = new_vlans_by_id[pt]['interface']
                            vlan_id = new_vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('add element bridge elan mdns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))
                    for pt in self.vlans_by_ifname.get(nic_name, {}).get('mdns_answers_passthroughs', []):
                        if pt not in new_vlan.get('mdns_answers_passthroughs', []):
                            # delete no longer existing passthrough
                            nic_out = self.vlans_by_id[pt]['interface']
                            vlan_id = self.vlans_by_id[pt]['vlan_id']
                            if vlan_id:
                                nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                            nft('delete element bridge elan mdns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    # Configure connection tracking
                    if new_vlan.get('log', False):
                        nft('add element bridge elan log_ifs {{ {nic} }}'.format(nic=nic_name))
                    else:
                        nft('delete element bridge elan log_ifs {{ {nic} }}'.format(nic=nic_name))

                    # Configure IDS
                    if new_vlan.get('ids', False):
                        nft('add element bridge elan ids_ifs {{ {nic} }}'.format(nic=nic_name))
                    else:
                        nft('delete element bridge elan ids_ifs {{ {nic} }}'.format(nic=nic_name))

                # VLANs to delete
                for nic_name in set(self.vlans_by_ifname.keys()) - set(new_vlans_by_ifname.keys()):
                    old_vlan = self.vlans_by_ifname[nic_name]
                    vlan_id = old_vlan.get('vlan_id', 0)

                    for pt in old_vlan.get('dhcp_passthroughs', []):
                        nic_out = self.vlans_by_id[pt]['interface']
                        vlan_id = self.vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('delete element bridge elan dhcp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    for pt in old_vlan.get('dns_passthroughs', []):
                        nic_out = self.vlans_by_id[pt]['interface']
                        vlan_id = self.vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('delete element bridge elan dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    for pt in old_vlan.get('ndp_passthroughs', []):
                        nic_out = self.vlans_by_id[pt]['interface']
                        vlan_id = self.vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('delete element bridge elan ndp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    for pt in old_vlan.get('mdns_answers_passthroughs', []):
                        nic_out = self.vlans_by_id[pt]['interface']
                        vlan_id = self.vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('delete element bridge elan mdns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                    for protocol in ['ip', 'ip6']:
                        nft("delete element {protocol} elan captive_portals {{ {mark} . 80, {mark} . 443 }}".format(protocol=protocol, mark=old_vlan['local_index']))

                    try:
                        nic = ip.interfaces[nic_name]
                        if vlan_id:
                            nic.remove()
                        else:
                            bridge.del_port(nic)
                    except:
                        # TODO log error to CC
                        print('error occured:', traceback.format_exc())

            # Set captive portals
            nginx_captive_portals = Template(filename='/elan-agent/network/nginx/server')
            with open("/etc/nginx/sites-enabled/captive-portal", "w") as nginx_file:
                nginx_file.write(nginx_captive_portals.render(vlans=new_vlans_by_ifname))

            reload_service('nginx')

            self.vlans_by_ifname = new_vlans_by_ifname
            self.vlans_by_id = new_vlans_by_id

            nac.set_access_controlled_vlans_cache([iface for iface, vlan in new_vlans_by_ifname.items() if vlan.get('access_control', False)])

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

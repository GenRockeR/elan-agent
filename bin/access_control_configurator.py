#!/usr/bin/env python3

from mako.template import Template
from pyroute2 import IPDB
import argparse
import os
import subprocess

from elan.event import ExceptionEvent
from elan.network import NetworkConfigurator, BRIDGE_NAME
from elan.neuron import Dendrite, Synapse, ConnectionFailed
from elan.utils import reload_service, physical_ifaces

NGINX_CAPTIVE_PORTAL = "/etc/nginx/sites-enabled/captive-portal"


class AccessControlConfigurator():

    def __init__(self):

        self.agent_path = None
        self.vlans_path = None

        self.vlans_by_ifname = {}  # vlans by NIC name (<nic>.<vlan>)
        self.vlans_by_id = {}  # vlans by Vlan-ID

    def new_vlan_conf(self, vlans, skip_vlans_conf_files=False):
        # conf is list of all VLANS -> when a Vlan is modified, all VLANs are sent
        new_vlans_by_ifname = {}
        new_vlans_by_id = {}
        for vlan in vlans:
            if 'id' in vlan:
                new_vlans_by_id[vlan['id']] = vlan
            if vlan.get('vlan_id', 0):
                nic_name = '{nic}.{vid}'.format(nic=vlan['interface'], vid=vlan['vlan_id'])
            else:
                nic_name = vlan['interface']
            new_vlans_by_ifname[ nic_name ] = vlan

        ip = IPDB(mode='explicit')

        # Configure New VLANs
        # TODO: use nft from pyroute2 when ready... meanwhile, create a manager to handle 'quit' command...
        with subprocess.Popen(['nft', '-i'], stdin=subprocess.PIPE, universal_newlines=True, stdout=subprocess.DEVNULL) as nft_process:

            def nft(cmd):
                print(cmd, file=nft_process.stdin, flush=True)

                if cmd == 'quit':
                    try:
                        nft_process.wait(2)
                    except subprocess.TimeoutExpired:
                        pass

            # Flush some sets we use, they will be re-populated after.
            # ac_ifs, ids_ifs and log_ifs are left alone as we do not want to remove access control or miss a connection when changing VLANs
            for nft_set in ['dhcp_pt_ifs', 'dns_pt_ifs', 'ndp_pt_ifs', 'mdns_pt_ifs']:
                nft('flush set bridge elan {nft_set}'.format(nft_set=nft_set))
            for protocol in ['ip', 'ip6']:
                nft("flush map {protocol} elan captive_portals".format(protocol=protocol))

            bridge = ip.interfaces[BRIDGE_NAME]
            bridge.begin()

            if not skip_vlans_conf_files:
                NetworkConfigurator.generate_vlans_conf_files(vlans)

            # VLANs to delete
            for nic_name in set(self.vlans_by_ifname.keys()) - set(new_vlans_by_ifname.keys()):
                old_vlan = self.vlans_by_ifname[nic_name]
                vlan_id = old_vlan.get('vlan_id', 0)

                nft('delete element bridge elan ac_ifs  {{ {nic} }}'.format(nic=nic_name))
                nft('delete element bridge elan ids_ifs {{ {nic} }}'.format(nic=nic_name))
                nft('delete element bridge elan log_ifs {{ {nic} }}'.format(nic=nic_name))

                # Netplan does not delete virtual interfaces it created nor remove them from the bridge:
                try:
                    nic = ip.interfaces[nic_name]
                    if vlan_id:
                        nic.begin()
                        nic.remove().commit()
                    else:
                        bridge.del_port(nic)
                except:
                    ExceptionEvent(source='access_control_configurator').notify()

            bridge.commit()

            # apply new conf so netplan creates new virtual interfaces for vlans and puts them in the bridge
            NetworkConfigurator.reload()

            # Configure Vlans
            for nic_name, new_vlan in new_vlans_by_ifname.items():
                # configure Access Contol
                if new_vlan.get('access_control', False):
                    nft('add element bridge elan ac_ifs {{ {nic} }}'.format(nic=nic_name))
                else:
                    nft('delete element bridge elan ac_ifs {{ {nic} }}'.format(nic=nic_name))

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

                # configure DNS passthrough
                for pt in new_vlan.get('dns_passthroughs', []):
                    if pt not in self.vlans_by_ifname.get(nic_name, {}).get('dns_passthroughs', []):
                        # add non existing passthrough
                        nic_out = new_vlans_by_id[pt]['interface']
                        vlan_id = new_vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('add element bridge elan dns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                # configure ARP/NDP passthrough
                for pt in new_vlan.get('ndp_passthroughs', []):
                    if pt not in self.vlans_by_ifname.get(nic_name, {}).get('ndp_passthroughs', []):
                        # add non existing passthrough
                        nic_out = new_vlans_by_id[pt]['interface']
                        vlan_id = new_vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('add element bridge elan ndp_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

                # configure mDNS passthroughs
                for pt in new_vlan.get('mdns_answers_passthroughs', []):
                    if pt not in self.vlans_by_ifname.get(nic_name, {}).get('mdns_answers_passthroughs', []):
                        # add non existing passthrough
                        nic_out = new_vlans_by_id[pt]['interface']
                        vlan_id = new_vlans_by_id[pt]['vlan_id']
                        if vlan_id:
                            nic_out = '{nic}.{vlan_id}'.format(nic=nic_out, vlan_id=vlan_id)
                        nft('add element bridge elan mdns_pt_ifs {{ {nic} . {nic_out} }}'.format(nic=nic_name, nic_out=nic_out))

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

            nft('quit')

        self.vlans_by_ifname = new_vlans_by_ifname
        self.vlans_by_id = new_vlans_by_id

        # Set captive portals
        nginx_captive_portals = Template(filename='/elan-agent/network/nginx/server')
        with open(NGINX_CAPTIVE_PORTAL, "w") as nginx_file:
            nginx_file.write(nginx_captive_portals.render(vlans=new_vlans_by_ifname))

        reload_service('nginx')

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--default-conf-only",
                        help="just generate default configuration if needed",
                        action="store_true")
    args = parser.parse_args()

    dendrite = Dendrite()

    try:
        vlans = dendrite.get_conf('vlans', timeout=5)
    except ConnectionFailed:
        vlans = None

    if vlans is None:
        # Default vlan conf: first 2 interfaces bridged
        default_vlans = []
        count = 0
        for interface in physical_ifaces():
            count += 1
            default_vlans.append({'interface': interface})
            if count == 2:
                break
        if args.default_conf_only and not NetworkConfigurator.vlans_conf_files_exists():
            NetworkConfigurator.generate_vlans_conf_files(default_vlans)

    if not args.default_conf_only:
        configurator = AccessControlConfigurator()
        # Generate nginx captive portal conf if needed
        if vlans is None and not os.path.exists(NGINX_CAPTIVE_PORTAL):
            configurator.new_vlan_conf(
                    default_vlans,
                    skip_vlans_conf_files=True
            )
        dendrite.subscribe_conf('vlans', cb=configurator.new_vlan_conf)

        # wait for changes
        dendrite.wait_complete()

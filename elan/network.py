from dns import resolver
from mako.template import Template
from pyroute2 import IPRoute
from pyroute2.netlink import rtnl
from watchdog.events import FileSystemEventHandler
import os.path
import socket
import subprocess
import watchdog.observers

from elan.neuron import Dendrite, ConnectionFailed

BRIDGE_NAME = 'elan'

IPv4_CONF_TOPIC = 'ipv4'
IPv4_CURRENT_TOPIC = 'ipv4/current'
IPv6_CONF_TOPIC = 'ipv6'
IPv6_CURRENT_TOPIC = 'ipv4/current'

DEFAULT_IPv4_CONF = {'type': 'dhcp', 'dns': [] }
DEFAULT_IPv6_CONF = {'type': 'autoconf', 'dns': [] }

RESOLV_FILE = '/run/systemd/resolve/resolv.conf'


class NetworkConfiguration:
    'Class to manipulate IP configuration and retrieve current status'
    dendrite = Dendrite()

    def get_current_ips(self, cidr=False):
        ips = self.get_current_ipv4()['ips'] + self.get_current_ipv6()['ips']
        if not cidr:
            ips = [ip.split('/')[0] for ip in self.get_current_ipv4()['ips'] + self.get_current_ipv6()['ips']]

        return ips

    def get_current_ipv4(self):
        return self.dendrite.get_conf(IPv4_CURRENT_TOPIC) or {'ips': [], 'gw': None, 'dns': []}

    def get_ipv4_conf(self):
        return self.dendrite.get_conf(IPv4_CONF_TOPIC) or DEFAULT_IPv4_CONF

    def set_ipv4_conf(self, conf):
        self.dendrite.publish_conf(IPv4_CONF_TOPIC, conf)

    def get_current_ipv6(self):
        return self.dendrite.get_conf(IPv6_CURRENT_TOPIC) or {'ips': [], 'gw': None, 'dns': []}

    def get_ipv6_conf(self):
        return self.dendrite.get_conf(IPv6_CONF_TOPIC) or DEFAULT_IPv6_CONF

    def set_ipv6_conf(self, conf):
        self.dendrite.publish_conf(IPv6_CONF_TOPIC, conf)


class NetworkMonitor:
    '''
    class that will monitor and interface and publish current configuration (IPs, default gateway, and DNS)
    '''
    dendrite = Dendrite()

    def __init__(self, interface=BRIDGE_NAME, ipv4_topic=IPv4_CURRENT_TOPIC, ipv6_topic=IPv6_CURRENT_TOPIC):
        self.interface = interface

        self.ipv4_topic = ipv4_topic
        self.ipv6_topic = ipv6_topic

        self.current_ipv4 = self.dendrite.get_conf(self.ipv4_topic) or {'ips':[], 'gw': None, 'dns': []}
        self.current_ipv6 = self.dendrite.get_conf(self.ipv6_topic) or {'ips':[], 'gw': None, 'dns': []}

    def run(self):

        with IPRoute() as ipr:
            # Bind before we get current values so that is they changed, we will be notified.
            ipr.bind(groups=
                        rtnl.RTNLGRP_IPV4_IFADDR |
                        rtnl.RTNLGRP_IPV6_IFADDR |
                        rtnl.RTNLGRP_IPV4_ROUTE |
                        rtnl.RTNLGRP_IPV6_ROUTE
            )

            # all current values and publich after
            self.check_ips(publish=False)
            self.check_gw4(publish=False)
            self.check_gw6(publish=False)
            self.check_dns(publish=False)

            self.publish_current_ipv4()
            self.publish_current_ipv6()

            # set monitoring of DNS (executed in another thread)
            observer = watchdog.observers.Observer()
            observer.schedule(self.FileChangeHandler(file=RESOLV_FILE, moved_cb=self.check_dns, created_cb=self.check_dns),
                              path=os.path(RESOLV_FILE),
                              recursive=False
            )

            # monitor network Changes
            while True:
                events = ipr.get()
                for event in events:
                    if event['event'] in ['RTM_NEWROUTE', 'RTM_DELROUTE']:
                        if event['family'] == socket.AF_INET:
                            self.check_gw4()
                        elif event['family'] == socket.AF_INET6:
                            self.check_gw6()

                    elif event['event'] in ['RTM_NEWADDR', 'RTM_DELADDR'] and event['index'] == ipr.link_lookup(ifname=self.interface)[0]:
                        self.check_ips(ipr)

    def check_gw4(self, publish=True):
        gw4 = self.get_gw4()
        if self.current_ipv4['gw'] != gw4:
            self.current_ipv4['gw'] = gw4
            if publish:
                self.publish_current_ipv4()

    def check_gw6(self, publish=True):
        gw6 = self.get_gw6()
        if self.current_ipv6['gw'] != gw6:
            self.current_ipv6['gw'] = gw6
            if publish:
                self.publish_current_ipv6()

    def check_ips(self, publish=True):
        ips = self.get_ips(self.interface)

        ipv4s = [ip for ip in ips if '.' in ip]
        if set(self.current_ipv4['ips']) != set(ipv4s):
            self.current_ipv4['ips'] = ipv4s
            if publish:
                self.publish_current_ipv4()

        ipv6s = [ip for ip in ips if '.' in ip]
        if set(self.current_ipv6['ips']) != set(ipv6s):
            self.current_ipv6['ips'] = ipv6s
            if publish:
                self.publish_current_ipv6()

    def check_dns(self, publish=True):
        dns = self.parse_resolvconf(RESOLV_FILE)

        dns4 = [d for d in dns if '.' in d]
        if dns4 != self.current_ipv4['dns']:
            self.current_ipv4['dns'] = dns4
            if publish:
                self.publish_current_ipv4()

        dns6 = [d for d in dns if '.' in d]
        if dns6 != self.current_ipv6['dns']:
            self.current_ipv6['dns'] = dns6
            if publish:
                self.publish_current_ipv6()

    class FileChangeHandler(FileSystemEventHandler):

        def __init__(self, file, created_cb, moved_cb):
            self.file = file
            self.created_cb = created_cb
            self.moved_cb = moved_cb

        def on_moved(self, event):
            if event.dest_path == self.file:
                self.moved_cb()

        def on_created(self, event):
            if event.src_path == self.file:
                self.created_cb()

    def get_ips(self, interface):
        ipr = IPRoute()

        ips = set()
        index = ipr.link_lookup(ifname=interface)[0]
        for entry in ipr.get_addr(index=index):
            for key, value in entry['attrs']:
                if key == 'IFA_ADDRESS':
                    ip = '{ip}/{mask}'.format(ip=value, mask=entry['prefixlen'])
                    ips.add(ip)
                break

        return ips

    def get_gw4(self):
        try:
            return resolver.query('_gateway', 'A')[0].address
        except:
            return None

    def get_gw6(self):
        try:
            return resolver.query('_gateway', 'AAAA')[0].address
        except:
            return None

    def parse_resolconf(self, file=RESOLV_FILE):
        dns = []
        try:
            with open(file) as resolvconf:
                for line in resolvconf:
                    if line.startswith('nameserver '):
                        line = line.rstrip()
                        dns += [n for n in line.split()[1:] if n]
        except FileNotFoundError:
            pass

        return dns

    def publish_current_ipv4(self):
        self.dendrite.publish_conf(self.ipv4_topic, self.current_ipv4)

    def publish_current_ipv6(self):
        self.dendrite.publish_conf(self.ipv6_topic, self.current_ipv6)


class NetworkConfigurator:
    'Class that does apply the network configuration. Use NetworkConfiguration class to manipulate Network Configuration'
    ip_conf_template = '/elan-agent/network/netplan-ip-conf.yaml'
    vlans_conf_template = '/elan-agent/network/netplan-vlans.yaml'
    ip_conf_file = '/etc/network/elan-ip-conf.yaml'
    vlans_conf_file = '/etc/network/elan-vlans.yaml'
    dendrite = Dendrite()

    def __init__(self):
        self.load_configuration()

    def load_configuration(self):
        try:
            self.ipv4 = self.dendrite.get_conf(IPv4_CONF_TOPIC)
            if self.ipv4 is None:
                self.ipv4 = DEFAULT_IPv4_CONF

            self.ipv6 = self.dendrite.get_conf(IPv6_CONF_TOPIC)
            if self.ipv6 is None:
                self.ipv6 = DEFAULT_IPv6_CONF
        except ConnectionFailed:
            if os.path.exists(self.ip_conf_file):
                self.ipv4 = None
                self.ipv6 = None
            else:
                self.ipv4 = DEFAULT_IPv4_CONF
                self.ipv6 = DEFAULT_IPv6_CONF

    def set_ipv4(self, kwargs):
        self.ipv4 = kwargs
        self.apply_ip_conf()

    def set_ipv6(self, kwargs):
        self.ipv6 = kwargs
        self.apply_ip_conf()

    def apply_ip_conf(self):
        if self.ipv4 is not None and self.ipv6 is not None:
            self.generate_ip_conf_files(ipv4_conf=self.ipv4, ipv6_conf=self.ipv6)
        self.reload()

    @classmethod
    def generate_ip_conf_files(cls, ipv4_conf, ipv6_conf):
        template = Template(filename=cls.ip_conf_template)

        with open(cls.ip_conf_file, 'w') as conf_file:
            conf_file.write(template.render(ipv4=ipv4_conf, ipv6=ipv6_conf, bridge_name=BRIDGE_NAME))

    @classmethod
    def generate_vlans_conf_files(cls, vlans):
        template = Template(filename=cls.vlans_conf_template)

        with open(cls.vlans_conf_file, 'w') as conf_file:
            conf_file.write(template.render(vlans=vlans, bridge_name=BRIDGE_NAME))

    @staticmethod
    def reload():
        subprocess.run('netplan apply')

from mako.template import Template
import os.path
import subprocess

from elan.neuron import Dendrite, ConnectionFailed

BRIDGE_NAME = 'elan'

IPv4_CONF_TOPIC = 'ipv4'
IPv4_CURRENT_TOPIC = 'ipv4/current'
IPv6_CONF_TOPIC = 'ipv6'
IPv6_CURRENT_TOPIC = 'ipv4/current'

DEFAULT_IPv4_CONF = {'type': 'dhcp', 'dns': [] }
DEFAULT_IPv6_CONF = {'type': 'autoconf', 'dns': [] }


class NetworkConfiguration:
    'Class to manipulate IP configuration and retrieve current status'
    dendrite = Dendrite()

    def get_current_ipv4(self):
        return self.dendrite.get_conf(IPv4_CURRENT_TOPIC)

    def get_ipv4_conf(self):
        return self.dendrite.get(IPv4_CONF_TOPIC) or DEFAULT_IPv4_CONF

    def set_ipv4_conf(self, conf):
        self.dendrite.publish_conf(IPv4_CONF_TOPIC, conf)

    def get_current_ipv6(self):
        return self.dendrite.get_conf(IPv6_CURRENT_TOPIC)

    def get_ipv6_conf(self):
        return self.dendrite.get(IPv6_CONF_TOPIC) or DEFAULT_IPv6_CONF

    def set_ipv6_conf(self, conf):
        self.dendrite.publish_conf(IPv6_CONF_TOPIC, conf)


class NetworkMonitor:
    pass


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
            self.ipv4 = self.dendrite.get_conf(self.IPv4_CONF_PATH)
            if self.ipv4 is None:
                self.ipv4 = DEFAULT_IPv4_CONF

            self.ipv6 = self.dendrite.get_conf(self.IPv6_CONF_PATH)
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

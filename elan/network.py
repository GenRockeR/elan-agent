from mako.template import Template
import os.path

from elan.neuron import Synapse, is_synapse_ready, wait_for_synapse_ready
from elan.utils import restart_service, stop_service, start_service


class NetworkConfiguration:
    IPv4_CONF_PATH = 'conf:network:ipv4'
    IPv6_CONF_PATH = 'conf:network:ipv6'
    DEFAULT_IPv4_CONF = {'type': 'dhcp', 'dns': [] }
    DEFAULT_IPv6_CONF = {'type': 'autoconf', 'dns': [] }
    configuration_template = '/elan-agent/network/interfaces'
    configuration_file = '/etc/network/interfaces.d/elan-network'
    synapse = Synapse()

    def __init__(self, wait_synapse=True):
        self.load_configuration(wait_synapse)

    def load_configuration(self, wait_synapse=True):
        if wait_synapse:
            wait_for_synapse_ready(self.synapse)

        if is_synapse_ready(self.synapse):
            self.ipv4 = self.synapse.get(self.IPv4_CONF_PATH)
            if self.ipv4 is None:
                self.ipv4 = self.DEFAULT_IPv4_CONF

            self.ipv6 = self.synapse.get(self.IPv6_CONF_PATH)
            if self.ipv6 is None:
                self.ipv6 = self.DEFAULT_IPv6_CONF
        elif os.path.exists(self.configuration_file):
            self.ipv4 = None
            self.ipv6 = None
        else:
            self.ipv4 = self.DEFAULT_IPv4_CONF
            self.ipv6 = self.DEFAULT_IPv6_CONF

    def save_configuration(self):
        self.synapse.set(self.IPv4_CONF_PATH, self.ipv4)
        self.synapse.set(self.IPv6_CONF_PATH, self.ipv6)

    def apply_configuration(self):
        stop_service('elan-network', sudo=True)  # bring down br0 with old config to deconfigure it properly (DHCP release...)
        self.generate_configuration_files()
        start_service('elan-network', no_block=True, sudo=True)

    def generate_configuration_files(self):
        if self.ipv4 is not None:
            template = Template(filename=self.configuration_template)

            with open(self.configuration_file, 'w') as conf_file:
                conf_file.write(template.render(ipv4=self.ipv4, ipv6=self.ipv6))

    def set_ip_v4(self, kwargs):
        self.ipv4 = kwargs
        self.save_configuration()
        self.apply_configuration()

    def set_ip_v6(self, kwargs):
        self.ipv6 = kwargs
        self.save_configuration()
        self.apply_configuration()

    @classmethod
    def reload(cls):
        restart_service('elan-network', no_block=True, sudo=True)

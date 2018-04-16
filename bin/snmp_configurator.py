#!/usr/bin/env python3

from mako.template import Template
import logging

from elan.neuron import Dendrite, Synapse
from elan.utils import restart_service

SNMP_DEFAULT_CREDENTIALS_PATH = 'snmp:default_credentials'

logging.basicConfig()


class SnmpConfigurator():
    KEYS = ('credentials', 'engine_ids')

    def __init__(self):
        self.conf = {}
        self.synapse = Synapse()

    def agent_conf_updated(self, conf):
        conf_changed = False

        for key in self.KEYS:
            if self.conf.get(key, {}) != conf[key]:
                self.conf[key] = conf[key]
                conf_changed = True

                # save credentials for other program use...
                if key == 'credentials':
                    self.synapse.set(SNMP_DEFAULT_CREDENTIALS_PATH, conf[key])

        if conf_changed:
            # Grab template
            snmp_template = Template(filename="/elan-agent/nac/snmp/snmptrapd.conf")

            with open ("/etc/snmp/snmptrapd.conf", "w") as server_file:
                server_file.write(snmp_template.render(**self.conf))

            # Reload freeradius
            restart_service('snmptrapd')


if __name__ == "__main__":
    dendrite = Dendrite()
    conf = SnmpConfigurator()
    dendrite.subscribe_conf('snmp', conf.agent_conf_updated)

    dendrite.wait_complete()

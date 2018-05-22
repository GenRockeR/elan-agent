#!/usr/bin/env python3

from mako.template import Template
import logging

from elan.neuron import Dendrite, Synapse
from elan.utils import restart_service

logging.basicConfig()


class RadiusConfigurator():
    KEYS = ('dot1x_authentication', 'default_secret', 'ca_cert', 'cert_key', 'cert_chain')

    def __init__(self):
        self.conf = {}
        self.synapse = Synapse()

    def agent_conf_updated(self, conf):
        conf_changed = False

        for key in self.KEYS:
            if self.conf.get(key, "") != conf[key]:
                self.conf[key] = conf[key]
                conf_changed = True

        if conf_changed:
            # Grab template
            server_template = Template(filename="/elan-agent/nac/freeradius/server")

            with open ("/etc/freeradius/3.0/sites-enabled/nac", "w") as server_file:
                server_file.write(server_template.render(**self.conf))

            with open ("/etc/freeradius/3.0/certs/nac.pem", "w") as cert_file:
                # reverse certchain so that freeradius/openssl finds the cert matching the private key in first position...
                cert_list = [ cert + '-----END CERTIFICATE-----\n' for cert in self.conf['cert_chain'].split('-----END CERTIFICATE-----') if '-----BEGIN CERTIFICATE-----' in cert ]
                cert_file.write(''.join(reversed(cert_list)))
                cert_file.write(self.conf['cert_key'])

            # Reload freeradius
            restart_service('freeradius')


if __name__ == "__main__":
    dendrite = Dendrite()
    conf = RadiusConfigurator()
    dendrite.subscribe_conf('radius', conf.agent_conf_updated)

    dendrite.wait_complete()

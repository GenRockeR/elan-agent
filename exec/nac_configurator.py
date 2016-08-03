#!/usr/bin/env python3

from origin.neuron import Dendrite, Synapse
from origin.utils import restart_service
from mako.template import Template

SNMP_DEFAULT_CREDENTIALS_PATH = 'snmp:default_credentials'

import logging
logging.basicConfig()

class NacConfigurator():
    FREERADIUS_KEYS = ('dot1x_authentication', 'default_secret', 'ca_cert', 'cert_key', 'cert_chain')
    SNMPTRAPD_KEYS  = ('snmp_credentials', 'snmp_engine_ids')
    
    def __init__(self):
        self.conf = {}
        self.synapse = Synapse()

    def agent_conf_updated(self, conf):
        freeradius_conf_changed = False
        snmptrapd_conf_changed = False

        for key in self.FREERADIUS_KEYS:
            if self.conf.get(key, "") != conf[key]:
                self.conf[key] = conf[key]
                freeradius_conf_changed = True

        for key in self.SNMPTRAPD_KEYS:
            if self.conf.get(key, {}) != conf[key]:
                self.conf[key] = conf[key]
                snmptrapd_conf_changed = True
                
                # save credentials for other program use...
                if key == 'snmp_credentials':
                    self.synapse.set(SNMP_DEFAULT_CREDENTIALS_PATH, conf[key])
                    

        if freeradius_conf_changed:
            # Grab template
            server_template = Template(filename="/origin/nac/freeradius/server")
            
            with open ("/etc/freeradius/sites-enabled/nac", "w") as server_file:
                server_file.write( server_template.render(**self.conf) )
                
            with open ("/etc/freeradius/certs/nac.pem", "w") as cert_file:
                # reverse certchain so that freeradius/openssl finds the cert matching the private key in first position...
                cert_list = [ cert + '-----END CERTIFICATE-----\n' for cert in self.conf['cert_chain'].split('-----END CERTIFICATE-----') if '-----BEGIN CERTIFICATE-----' in cert ]
                cert_file.write( ''.join(reversed(cert_list)) )
                cert_file.write( self.conf['cert_key'] )

            # Reload freeradius
            restart_service('freeradius')

        if snmptrapd_conf_changed:
            # Grab template
            snmp_template = Template(filename="/origin/nac/snmp/snmptrapd.conf")
            
            with open ("/etc/snmp/snmptrapd.conf", "w") as server_file:
                server_file.write( snmp_template.render(**self.conf) )

            # Reload freeradius
            restart_service('freeradius')

if __name__ == "__main__":
    dendrite = Dendrite()
    conf = NacConfigurator()
    dendrite.subscribe_conf('agent', conf.agent_conf_updated)

    dendrite.wait_complete()

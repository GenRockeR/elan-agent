import pyrad.packet
from pyrad.client import Client
from pyrad.dictionary import Dictionary
import time, subprocess, re
from origin.neuron import Dendrite
from mako.template import Template



def pwd_authenticate(authenticator_id, user, pwd):
    srv = Client(server="127.0.0.1", authport=18122, secret=b'a2e4t6u8qmlskdvcbxnw',
                 dict=Dictionary("/origin/authentication/pyradius/dictionary"))
    
    req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,
              User_Name=user, Connect_Info='authenticator={}'.format(authenticator_id) )
    req["User-Password"]=req.PwCrypt(pwd)
    
    reply = srv.SendPacket(req)
    
    if 'Reply-Message' in reply:
        # TODO: 
        # - this should send event to CC login the fact there was an error...
        # This does not always mean authentication failed (in an auth group the following auth provider may have succeeded)
        # Or do this directly from FR....
        # - In reply Message (or other ?), there should be the the auth provider ID that will be returned by this function... None in case of failure !   
        pass
    
    return reply.code == pyrad.packet.AccessAccept

class AuthenticationProvider(Dendrite):
    
    def __init__(self):
        super().__init__('authentication')

        self.agent_id = None
        self.providers = {} # indexed by id
        self.groups = {}  # indexed by id

        self.retrieve('agent/self')
        self.subscribe('authentication')


    def answer_cb(self, path, conf):
        conf_changed = False
        # update local configuration cache
        if path == 'agent/self':
            if self.agent_id != conf['id']:
                self.agent_id = conf['id']
                conf_changed = True
        elif path == 'authentication':
            new_groups = {}
            new_providers = {}
            for auth in conf:
                if auth['type'] == 'group':
                    new_groups[auth['id']] = auth
                else:
                    new_providers[auth['id']] = auth
            
            if new_groups != self.groups:
                self.groups = new_groups
                conf_changed = True 
            if new_providers != self.providers:
                self.providers = new_providers
                conf_changed = True 

        if self.agent_id and conf_changed: # we may receive agent id after conf
            # Grab templates
            policy_template = Template(filename="/origin/authentication/freeradius/policy")
            ldap_template = Template(filename="/origin/authentication/freeradius/ldap-module")
            cc_auth_template = Template('''
                update reply {
                    &Origin-Auth-Provider := ${id}
                }
                cc-auth {
                    fail = 1
                }
            ''')
            rest_conf = Template(filename="/origin/authentication/freeradius/rest-module")

            module_conf = rest_conf.render(agent_id=self.agent_id)
    
            inner_switch_server_conf = ""
            # Generate the files if we have all the information...
            new_provided_services = set()
            for provider in self.providers.values():
                if provider['type'] == 'LDAP':
                    if self.agent_id in provider['agents']:
                        module_conf += "\n" + ldap_template.render(**provider)
                        inner_switch_server_conf += '''
                            case {id} {{
                                update reply {{
                                    &Origin-Auth-Provider := {id}
                                }}
                                ldap-auth-{id} {{
                                    fail = 1
                                }}
                                if(fail) {{
                                    update reply {{
                                        Reply-Message += &Module-Failure-Message
                                    }}
                                    update request {{
                                        Module-Failure-Message !* ''
                                    }}
                                }}
                            }}
                        '''.format(**provider)
                        # also notify that we provide this auth
                        new_provided_services.add( 'authentication/provider/{id}/authenticate'.format(id=provider['id']) )
            for group in self.groups.values():
                first = True
                inner_case = ""
                for provider_id in group['providers']:
                    provider_conf = self.providers[ provider_id ]
                    if not first:
                        inner_case += "if( notfound || fail ) {\n"
                    if provider_conf['type'] == 'LDAP' and self.agent_id in provider_conf['agents']:
                        inner_case += '''
                        update reply {{
                            &Origin-Auth-Provider := {id}
                        }}
                        ldap-auth-{id} {{
                            fail = 1
                        }}
                        if(fail) {{
                            update reply {{
                                Reply-Message += &Module-Failure-Message
                            }}
                            update request {{
                                Module-Failure-Message !* ''
                            }}
                        }}
                        '''.format(**provider_conf)
                    else:
                        inner_case += cc_auth_template.render(**provider_conf)
                    if not first:
                        inner_case += "\n}\n"
                    else :
                        first = False
                inner_switch_server_conf +=  '''
                        case {id} {{
                            {inner_case}
                        }}
                    '''.format(id=group['id'], inner_case=inner_case)
    
            with open ("/etc/freeradius/mods-enabled/authentications", "w") as module_file:
                module_file.write( module_conf )
            with open ("/etc/freeradius/policy.d/authentications", "w") as policy_file:
                policy_file.write( policy_template.render(inner_switch=inner_switch_server_conf) )
            
            # CAs
            for provider in self.provider_confs.values():
                if provider.get('server_ca', None):
                    with open ("/etc/freeradius/certs/server_CA/auth-{id}.pem".format(id=provider['id']), "w") as server_ca_file:
                        server_ca_file.write(provider['server_ca'])
    
            # unprovide
            for service_path in self.get_provided_services() - new_provided_services:
                self.unprovide(service_path)
                
            # Reload freeradius
            subprocess.call('restart freeradius || start freeradius', shell=True)
            
            # new provides
            for service_path in new_provided_services:
                self.provide(service_path)

    def call_cb(self, path, data):
        m = re.match(r'authentication/provider/(\d+)/authenticate', path)
        if m:
            # TODO: have a way to detect failure of provider (LDAP...) in FR ... via exception ? based on RADIUS Reply-Message ?
            try:
                return { 'success': pwd_authenticate(m.group(1), data['login'], data['password']) }
            except KeyError:
                return { 'success': False }

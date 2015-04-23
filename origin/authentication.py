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
        self.authentications = {} # indexed by id

        self.retrieve('agent/self')
        self.subscribe('authentication')
        
        self.policy_template = Template(filename="/origin/authentication/freeradius/policy")
        self.ldap_template = Template(filename="/origin/authentication/freeradius/ldap-module")
        self.cc_auth_template = Template('''
            update session-state {
                &Origin-Auth-Provider := ${id}
            }
            cc-auth {
                fail = 1
            }
        ''')
        self.ldap_auth_template = Template('''
            update session-state {
                &Origin-Auth-Provider := ${id}
            }
            ldap-auth-${id} {{
                fail = 1
            }
            if(fail) {
                update reply {
                    Reply-Message += &Module-Failure-Message
                }
                update request {
                    Module-Failure-Message !* ''
                }
            }
        ''')
        self.rest_conf = Template(filename="/origin/authentication/freeradius/rest-module")



    def get_group_inner_case(self, auth, ignore_authentications=None):
        if ignore_authentications is None:
            ignore_authentications = set()
        
        if auth['id'] in ignore_authentications:
            # authentications has already been tried. no need to try it again...
            return ''

        ignore_authentications.add(auth['id'])

        inner_case = ''
        
        if auth['type'] == 'group':
            for member_id in auth('members'):
                inner_case += self.get_group_inner_case( self.authentications[member_id], ignore_authentications )
        else:
            inner_case = 'if( notfound || fail ) {\n'   

            if auth['type'] == 'LDAP' and self.agent_id in auth['agents']:
                inner_case += self.ldap_auth_template.render(**auth)
            else:
                inner_case += self.cc_auth_template.render(**auth)
    
            inner_case += "\n}\n"
        
        return inner_case

    def answer_cb(self, path, conf):
        conf_changed = False
        # update local configuration cache
        if path == 'agent/self':
            if self.agent_id != conf['id']:
                self.agent_id = conf['id']
                conf_changed = True
        elif path == 'authentication':
            new_authentications = {}
            for auth in conf:
                new_authentications[auth['id']] = auth
            
            if new_authentications != self.authentications:
                self.authetications = new_authentications
                conf_changed = True 

        if self.agent_id and conf_changed: # we may receive agent id after conf
            # Grab templates
            module_conf = self.rest_conf.render(agent_id=self.agent_id)
    
            inner_switch_server_conf = ""
            # Generate the files if we have all the information...
            new_provided_services = set()
            
            for auth in self.authentications.values():
                if auth['type'] == 'LDAP' and self.agent_id in auth['agents']:
                    module_conf += "\n" + self.ldap_template.render(**auth)
                    inner_switch_server_conf += self.ldap_auth_template.render(**auth)
                    # also notify that we provide this auth
                    new_provided_services.add( 'authentication/provider/{id}/authenticate'.format(id=auth['id']) )
                elif auth['type'] == 'group':    
                    # Take care of groups, that can be nested:
                    inner_switch_server_conf +=  '''
                            case {id} {{
                                notfound
                                {inner_case}
                            }}
                    '''.format(
                           id = auth['id'],
                           inner_case = self.get_group_inner_case(auth) )


            with open ("/etc/freeradius/mods-enabled/authentications", "w") as module_file:
                module_file.write( module_conf )
            with open ("/etc/freeradius/policy.d/authentications", "w") as policy_file:
                policy_file.write( self.policy_template.render(inner_switch=inner_switch_server_conf) )
            
            # CAs
            for provider in self.authentications.values():
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

from mako.template import Template
from pyrad.client import Client, Timeout
from pyrad.dictionary import Dictionary
import pyrad.packet
import subprocess, re, socket

from elan.neuron import Synapse, Dendrite, RequestTimeout, RequestError
from elan.utils import restart_service


class AuthenticationFailed(Exception):
    pass


def pwd_authenticate(authenticator_id, login, password, source):
    '''
    Passsword authentication against RADIUS
    :param authenticator_id: Authentication ID to be used.
    :param login:
    :param password:
    :param source: Source that is asking for authentication. Used for error notifications
    :returns: Effective authenticator ID
    :raises AuthenticationFailed: when auth failed. May contain an error message (Reply Message sent back from RADIUS)
    '''
    srv = Client(server="127.0.0.1", authport=18122, secret=b'a2e4t6u8qmlskdvcbxnw',
                 dict=Dictionary("/elan-agent/authentication/pyradius/dictionary"))

    req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,
              User_Name=login, Connect_Info='authenticator={},source={},command=authenticate'.format(authenticator_id, source))
    req["User-Password"] = req.PwCrypt(password)

    try:
        reply = srv.SendPacket(req)
    except Timeout:
        raise RequestTimeout
    except Exception as e:
        raise RequestError(e)

    if reply.code == pyrad.packet.AccessAccept:
        if 'Reply-Message' in reply:
            m = re.search('provider=(?P<provider_id>\d+)', reply['Reply-Message'][0])
            if m:
                authenticator_id = m.group('provider_id')
        return authenticator_id

    errors = []
    if 'Reply-Message' in reply:
        errors = reply['Reply-Message']

    raise AuthenticationFailed(*errors)


def get_authorization(authenticator_id, login, source):
    srv = Client(server="127.0.0.1", authport=18122, secret=b'a2e4t6u8qmlskdvcbxnw',
                 dict=Dictionary("/elan-agent/authentication/pyradius/dictionary"))

    req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,
              User_Name=login, Connect_Info='authenticator={},source={},command=authorize'.format(authenticator_id, source))

    reply = srv.SendPacket(req)

    authz = {}

    for attr in reply.get(18, []):  # 18 -> Reply-Message
        key, value = attr.split('=', 1)
        if key == 'ELAN-Auth-Provider':
            key = 'provider'
        authz[key] = value

    return authz


class AuthenticationProvider():

    def __init__(self, dendrite=None):
        if dendrite is None:
            dendrite = Dendrite()
        self.dendrite = dendrite

        self.authentications = None
        self.provided_services = set()

        self.policy_template = Template(filename="/elan-agent/authentication/freeradius/policy")
        self.ldap_template = Template(filename="/elan-agent/authentication/freeradius/ldap-module")
        self.ad_template = Template(filename="/elan-agent/authentication/freeradius/ad-module")
        self.external_auth_template = Template('''
            update session-state {
                &ELAN-Auth-Provider := ${id}
            }
            external-auth {
                invalid = 1
                fail =  2
                reject = 3
                notfound = 4
                ok = return
                updated = return
            }
        ''')
        self.ldap_auth_template = Template('''
            update session-state {
                &ELAN-Auth-Provider := ${id}
            }
            ldap-auth-${id} {
                invalid = 1
                fail =  2
                reject = 3
                notfound = 4
                ok = return
                updated = return
            }
        ''')
        self.ad_auth_template = Template('''
            update session-state {
                &ELAN-Auth-Provider := ${id}
                &ELAN-AD-Auth-Provider := ${id}
            }
            ADldap {
                invalid = 1
                fail =  2
                reject = 3
                notfound = 4
                ok = return
                updated = return
            }
        ''')

    def get_group_inner_case(self, auth_id, ignore_authentications=None):
        if ignore_authentications is None:
            ignore_authentications = set()

        if auth_id in ignore_authentications:
            # authentications has already been tried. no need to try it again...
            return ''

        ignore_authentications.add(auth_id)

        inner_case = ''

        auth = self.authentications.get(auth_id, {'id': auth_id, 'type': 'external'})
        auth_type = auth.get('type', 'external')
        if auth_type == 'group':
            for member in auth['members']:
                member_auth = self.authentications.get(
                        member,
                        {'id': member, 'type': 'external'}  # external may not be declared
                )
                inner_case += self.get_group_inner_case(member_auth['id'], ignore_authentications)
        else:
            if auth_type == 'LDAP':
                inner_case += self.ldap_auth_template.render(**auth)
            elif auth_type == 'active-directory':
                inner_case += self.ad_auth_template.render(**auth)
            else:
                inner_case += self.external_auth_template.render(**auth)

            inner_case += '''
                    if(fail) {
                        update request {
                            ELAN-Auth-Failed := &session-state:ELAN-Auth-Provider
                        }
                        auth_provider_failed_in_group
                        update request {
                            Module-Failure-Message !* ANY
                        }
                    }
                    elsif(! invalid) {
                        update {
                            request:ELAN-Non-Failed-Auth := "True"
                        }
                    }
            '''

        return inner_case

    def new_authentication_conf(self, conf):
            new_authentications = {}
            for auth in conf:
                new_authentications[auth['id']] = auth

            if new_authentications != self.authentications:
                # TODO: be more relevant, ie when AD join failed and conf sent again to retry
                self.authentications = new_authentications
                self.apply_conf()

    def apply_conf(self):
        module_conf = '''
rest external-auth {
        connect_uri = "http://127.0.0.1:8080/authentication/"

        authorize {
                uri = "${..connect_uri}authorize?provider=%{%{session-state:ELAN-Auth-Provider}:-%{ELAN-Auth-Provider}}&source=%{ELAN-Auth-Type}"
                method = 'post'
                body = 'json'

        }
        authenticate {
                uri = "${..connect_uri}authenticate?provider=%{%{session-state:ELAN-Auth-Provider}:-%{ELAN-Auth-Provider}}&source=%{ELAN-Auth-Type}"
                method = 'post'
                body = 'json'

        }

        pool {
            start = 0
            min = ${thread[pool].min_spare_servers}
            max = ${thread[pool].max_servers}
            spare = ${thread[pool].max_spare_servers}
            uses = 0
            retry_delay = 30
            lifetime = 0
            idle_timeout = 0
        }
}

exec ADpap {
        wait = yes
        program = "/usr/bin/ntlm_auth --request-nt-key --domain=%{mschap:NT-Domain} --username=%{mschap:User-Name} --password=%{User-Password}"
}

mschap ADmschap {
     winbind_username = "%{mschap:User-Name}"
     winbind_domain = "%{mschap:NT-Domain}"

     pool {
        start = 0
        min = ${thread[pool].min_spare_servers}
        max = ${thread[pool].max_servers}
        spare = ${thread[pool].max_spare_servers}
        uses = 0
        retry_delay = 5
        lifetime = 86400
        cleanup_interval = 300
        idle_timeout = 600
    }

    passchange {
    }
    allow_retry = yes
    retry_msg = "Enter a valid password"

}

rest auth_provider_failed {
        connect_uri = "http://127.0.0.1:8080/authentication/provider/failed"

        authorize {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        authenticate {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        pool {
            start = 0
            min = ${thread[pool].min_spare_servers}
            max = ${thread[pool].max_servers}
            spare = ${thread[pool].max_spare_servers}
            uses = 0
            retry_delay = 30
            lifetime = 0
            idle_timeout = 0
        }
}
rest auth_provider_failed_in_group {
        connect_uri = "http://127.0.0.1:8080/authentication/provider/failed-in-group"

        authorize {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        authenticate {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        pool {
            start = 0
            min = ${thread[pool].min_spare_servers}
            max = ${thread[pool].max_servers}
            spare = ${thread[pool].max_spare_servers}
            uses = 0
            retry_delay = 30
            lifetime = 0
            idle_timeout = 0
        }
}


rest auth_all_providers_failed_in_group {
        connect_uri = "http://127.0.0.1:8080/authentication/group/all-failed"

        authorize {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        authenticate {
                uri = "${..connect_uri}"
                method = 'post'
                body = 'json'

        }
        pool {
            start = 0
            min = ${thread[pool].min_spare_servers}
            max = ${thread[pool].max_servers}
            spare = ${thread[pool].max_spare_servers}
            uses = 0
            retry_delay = 30
            lifetime = 0
            idle_timeout = 0
        }
}

'''

        inner_switch_server_conf = ""
        # Generate the files if we have all the information...
        new_provided_services = set()

        has_active_directory = False

        for auth in self.authentications.values():
            auth_type = auth.get('type', 'external')
            if auth_type == 'LDAP':
                module_conf += "\n" + self.ldap_template.render(**auth)
                inner_switch_server_conf += '''
                    case {id} {{
                '''.format(id=auth['id'])
                inner_switch_server_conf += self.ldap_auth_template.render(**auth)
                inner_switch_server_conf += '''
                        if(fail) {
                            update request {
                                ELAN-Auth-Failed := &session-state:ELAN-Auth-Provider
                            }
                            auth_provider_failed
                            update request {
                                Module-Failure-Message !* ANY
                            }
                        }
                    }
                '''
                # also notify that we provide this auth
                new_provided_services.add('authentication/provider/{id}/authenticate'.format(id=auth['id']))
                new_provided_services.add('authentication/provider/{id}/authorize'.format(id=auth['id']))
            elif auth_type == 'active-directory':
                # Join domain if not already done
                if not AD.joined(auth['domain']):
                    if AD.joined():
                        AD.leave()
                    # try to join
                    try:
                        AD.join(realm=auth['domain'], user=auth['adminLogin'], password=auth['adminPwd'])
                    except AD.Error as e:
                        status = {'status': 'error', 'error': e.message}
                    else:
                        status = {'status': 'joined'}
                    self.dendrite.publish_conf('authentication/provider/{id}/status'.format(id=auth['id']), status)

                if AD.joined(auth['domain']):
                    has_active_directory = True
                    inner_switch_server_conf += '''
                        case {id} {{
                    '''.format(id=auth['id'])
                    inner_switch_server_conf += self.ad_auth_template.render(**auth)
                    inner_switch_server_conf += '''
                            if(fail) {
                                update request {
                                    ELAN-Auth-Failed := &session-state:ELAN-Auth-Provider
                                }
                                auth_provider_failed
                                update request {
                                    Module-Failure-Message !* ANY
                                }
                            }
                        }
                    '''

                    module_conf += "\n" + self.ad_template.render(**AD.info())

                    # also notify that we provide this auth
                    new_provided_services.add('authentication/provider/{id}/authenticate'.format(id=auth['id']))
                    new_provided_services.add('authentication/provider/{id}/authorize'.format(id=auth['id']))
                else:
                    auth['join_failed'] = True  # so that if we receive again same conf, we try to join again (new condf!= old)

            elif auth_type == 'group':
                # Take care of groups, that can be nested:
                inner_switch_server_conf += '''
                        case {id} {{
                            group {{
                                {inner_case}
                                if( ! &ELAN-Non-Failed-Auth) {{
                                    auth_all_providers_failed_in_group
                                }}
                            }}
                        }}
                '''.format(
                       id=auth['id'],
                       inner_case=self.get_group_inner_case(auth['id']))

        # Quit AD domain if required
        if not has_active_directory and AD.joined():
            AD.leave()

        with open ("/etc/freeradius/3.0/mods-enabled/authentications", "w") as module_file:
            module_file.write(module_conf)
        with open ("/etc/freeradius/3.0/policy.d/authentications", "w") as policy_file:
            policy_file.write(self.policy_template.render(inner_switch=inner_switch_server_conf))

        # CAs
        for provider in self.authentications.values():
            if provider.get('server_ca', None):
                with open ("/etc/freeradius/3.0/certs/server_CA/auth-{id}.pem".format(id=provider['id']), "w") as server_ca_file:
                    server_ca_file.write(provider['server_ca'])

        # unprovide
        for service_path in self.provided_services - new_provided_services:
            self.dendrite.unprovide(service_path)

        # Reload freeradius
        restart_service('freeradius')

        # new provides
        for service_path in new_provided_services:
            self.dendrite.provide(service_path, cb=self.on_call)

        self.provided_services = new_provided_services

    def on_call(self, data, service):
        # TODO: make this async....
        m = re.match(r'authentication/provider/(\d+)/authenticate', service)
        if m:
            # TODO: have a way to detect failure of provider (LDAP...) in FR ... via exception ? based on RADIUS Reply-Message ?
            try:
                return { 'success': pwd_authenticate(m.group(1), login=data['login'], password=data['password'], source=data['source']) }
            except KeyError:
                return

        m = re.match(r'authentication/provider/(\d+)/authorize', service)
        if m:
            # TODO: have a way to detect failure of provider (LDAP...) in FR ... via exception ? based on RADIUS Reply-Message ?
            try:
                return get_authorization(m.group(1), login=data['login'], source=data['source'])
            except KeyError:
                return


class AD:
    synapse = Synapse()

    REDIS_INFO_PATH = 'authentication:AD:info'

    @classmethod
    def _run(cls, args):
        '''
        run command args as in subprocess.run
        returns a subprocess.CompletedProcess
        raises AD.Error with message as concatenation of stdout and stderr if return code != 0
        '''
        process_result = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
        )
        if process_result.returncode != 0:
            raise cls.Error(process_result.stdout + '\n' + process_result.stderr)

        return process_result

    @classmethod
    def joined(cls, realm=None):
        AD_info = cls.info()

        if AD_info:
            if realm:
                return realm.upper() == AD_info['realm'].upper()
            else:
                return True
        return False

    @classmethod
    def leave(cls):
        '''leave AD domain

            never fails
        '''
        try:
            cls._run(['net', '-P', 'ads', 'leave'])
        except cls.Error:
            pass

        cls.synapse.delete(cls.REDIS_INFO_PATH)

    @classmethod
    def join(cls, realm, user, password):
        cls._run(['net', 'conf', 'setparm', 'global', 'dedicated keytab file', '/etc/krb5.keytab'])
        cls._run(['net', 'conf', 'setparm', 'global', 'kerberos method', 'dedicated keytab'])
        cls._run(['net', 'ads', 'join', '-U', '{user}%{password}'.format(user=user, password=password), realm])
        restart_service('winbind')
        cls._run(['net', '-P', 'ads', 'keytab', 'create'])
        cls._run(['chown', 'freerad', '/etc/krb5.keytab'])
        cls._run(['usermod', '-a', '-G', 'winbindd_priv', 'freerad'])
        cls._run(['chgrp', 'winbindd_priv', '/var/lib/samba/winbindd_privileged'])

        f = open('/etc/freeradius/3.0/.k5identity', 'w')
        f.write('{hostname}$@{realm}'.format(hostname=socket.gethostname(), realm=realm).upper())
        f.close()

        process_result = cls._run(['net', '-P', 'ads', 'info'])

        info = {}
        for line in process_result.stdout.split('\n'):
            try:
                key, value = line.split(': ', 2)
            except ValueError:
                pass
            else:
                if key == 'LDAP server':
                    info['ldap_server_ip'] = value
                if key == 'LDAP server name':
                    info['ldap_server_name'] = value
                elif key == 'LDAP port':
                    info['ldap_port'] = value
                elif key == 'Bind Path':
                    info['ldap_base_dn'] = value
                elif key == 'Realm':
                    info['realm'] = value
        cls.synapse.set(cls.REDIS_INFO_PATH, info)

    @classmethod
    def info(cls):
        return cls.synapse.get(cls.REDIS_INFO_PATH)

    class Error(Exception):

        def __init__(self, message):
            self.message = message


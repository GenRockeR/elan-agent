from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.contrib.sites.models import get_current_site
from django.utils.translation import ugettext as _
from origin.captive_portal import GUEST_ACCESS_CONF_PATH, submit_guest_request, is_authz_pending, Administrator
from origin.neuron import Synapse, Axon, Dendrite
from origin.authentication import pwd_authenticate
from origin.utils import get_ip4_address, ip4_to_mac, is_iface_up
from origin import nac, session, utils

ADMIN_SESSION_IDLE_TIMEOUT = 300 #seconds

def requirePortalURL(fn):
    '''
    View decorator to make sure url used is the one of the agent and not the target URL 
    '''
    def wrapper(request, *args, **kwargs):
        agent_ip = get_ip4_address('br0')
        if str(get_current_site(request)) != agent_ip:
            return HttpResponseRedirect( 'http://' + agent_ip)
        return fn(request, *args, **kwargs)
    return wrapper



def redirect2status(request):
    if 'vlan_id' in request.META:
        return redirect('status')
    return redirect('dashboard')

@requirePortalURL
@never_cache
def status(request):
    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip4_to_mac(clientIP)
    if not nac.macAllowed(clientMAC, request.META['vlan_id']):
        return redirect('login')
    
    guest_access = request.META['guest_access']
    guest_access_conf = Synapse().hget(GUEST_ACCESS_CONF_PATH, guest_access)
    web_authentication = request.META['web_authentication']
    context={'guest_access': guest_access_conf, 'web_authentication': web_authentication}
    
    return render(request, 'captive-portal/status.html', context)

@requirePortalURL
def login(request):
    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip4_to_mac(clientIP)
    vlan_id = request.META['vlan_id']
    
    if nac.macAllowed(clientMAC, vlan_id):
        return redirect('status')

    
    guest_access = request.META['guest_access']
    guest_access_conf = Synapse().hget(GUEST_ACCESS_CONF_PATH, guest_access)
    web_authentication = request.META['web_authentication']
    context={ 'guest_access': guest_access_conf,
              'guest_access_pending': is_authz_pending(clientMAC, vlan_id),
              'web_authentication': web_authentication,
            }
    
    if request.method != 'POST':
        return render(request, 'captive-portal/login.html', context)
    
    # POST
    try:
        username = request.POST['username']
        password = request.POST['password']
    except (KeyError):
        # Redisplay the login form.
        context['error_message'] = _("'username' or 'password' missing.")
        return render(request, 'captive-portal/login.html', context )
    
    context['username'] = username
    if not pwd_authenticate(web_authentication, username, password):
        context['error_message'] = _("Invalid username or password.")
        return render(request, 'captive-portal/login.html', context)

    # start session
    # TODO: use effective auth_provider, this one could be a group 
    session.start_authorization_session(mac=clientMAC, vlan=vlan_id, type='web', login=username, authentication_provider=web_authentication, till_disconnect=True)
    nac.allowMAC(clientMAC, vlan_id, disallow_mac_on_disconnect=True)
    
    return redirect('status')


@requirePortalURL
def logout(request):
    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip4_to_mac(clientIP)
    nac.disallowMAC(clientMAC, request.META['vlan_id'])
    
    return redirect('login')

@requirePortalURL
def guest_access(request):
    if request.method != 'POST':
        return redirect('login')
    
    vlan = request.META['vlan'] # cc agent vlan *object* ID
    guest_access = request.META['guest_access'] 
    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip4_to_mac(clientIP)
    synapse = Synapse()

    # Guest access fields
    guest_access_conf = synapse.hget(GUEST_ACCESS_CONF_PATH, guest_access)
    guest_registration_fields = guest_access_conf['registration_fields'] 

    guest_request_fields = request.POST
    
    guest_request = dict(mac=clientMAC, vlan=vlan, fields=[], sponsor_email=guest_request_fields.get('sponsor_email', ''))
    for field in guest_registration_fields:
        guest_request['fields'].append( dict(display_name=field['display_name'], type=field['type'], value=guest_request_fields.get(field['display_name'], '')) )
    
    submit_guest_request(guest_request)

    return redirect('status')


# Session function helpers
def admin_session_login(session, login):
    session['admin'] = login
    session.set_expiry(ADMIN_SESSION_IDLE_TIMEOUT)

def admin_session_logout(session):
    del session['admin']
    session.set_expiry(None)

def save_admin_session_decorator(fn):
    def wrapper(request, *args, **kwargs):
        if request.session.get('admin', None):
            request.session.modified = True
        return fn(request, *args, **kwargs)
    return wrapper


@save_admin_session_decorator
def dashboard(request, context={}):
    context.update(
               is_connected = Axon.is_connected(),
               is_admin = bool(request.session.get('admin', False)),
               wan_up = is_iface_up('eth0'),
               lan_up = is_iface_up('eth1'),
               is_registered = Axon.is_registered(),
               ipsv4 = [utils.get_ip4_address('br0')],
               ipsv6 = utils.get_ip6_global_addresses('br0')
    )
    if not context.get('location', ''):
        context['location'] = Axon.agent_location() or ''

    
    return render(request, 'captive-portal/dashboard.html', context)

def admin_logout(request):
    admin_session_logout(request.session)
    
    return redirect('dashboard')


def admin_login(request):
    if request.method != 'POST':
        return redirect('dashboard')

    context = {}                    
    post_dict = request.POST.dict()

    if not Axon.is_registered():
        dendrite = Dendrite('dashboard')
        response = dendrite.sync_register(post_dict)
        if response['error']:
            context.update(field_errors = response['data'])
            if '__all__' in context['field_errors']:
                # Template Engine does not like variables starting with double underscores (__)
                context['errors'] = context['field_errors']['__all__']
        else:
            # Registration succeeded -> redirect to same to avoid repost
            admin_session_login(request.session, post_dict['login'])
            return redirect('dashboard')
    else:
        # Authenticate admin
        login = post_dict.get('login', None)
        if login:
            admin = Administrator.get(login)
            if admin and admin.check_password(request.POST.get('password', None)):
                admin_session_login(request.session, login)
                return redirect('dashboard')
        
        context['errors'] = [_('Invalid Credentials')]

    context.update(**post_dict)
    return dashboard(request, context)

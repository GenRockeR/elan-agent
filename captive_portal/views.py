from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.contrib.sites.models import get_current_site
from django.utils.translation import ugettext as _
from origin.captive_portal import GUEST_ACCESS_CONF_PATH, submit_guest_request, is_authz_pending
from origin.neuron import Synapse, Axon, Dendrite
from origin.authentication import pwd_authenticate
from origin.utils import get_ip4_address, ip4_to_mac, is_iface_up
from origin import nac, session, utils

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

def dashboard(request):
    context = {}
    
    if request.method == 'POST':
        if not Axon.is_registered():
            dendrite = Dendrite('dashboard')
            response = dendrite.sync_register(
                          { k:request.POST.get(k, '') for k in ('location', 'login', 'password', 'radius_secret') }
            )
            if response['error']:
                context.update(registration_errors = response['data'])
                if '__all__' in context['registration_errors']:
                    # Template Engine does not like variable sstart with doubl eunderscore (__)
                    context['registration_errors']['all_fields'] = context['registration_errors']['__all__']
        else:
            # TODO: Login ...
            pass
    
    context.update(
               is_connected = Axon.is_connected(),
               wan_up = is_iface_up('eth0'),
               lan_up = is_iface_up('eth1'),
               is_registered = Axon.is_registered(),
               location = Axon.agent_location() or '',
               ipsv4 = [utils.get_ip4_address('br0')],
               ipsv6 = utils.get_ip6_global_addresses('br0')
   )
    
    return render(request, 'captive-portal/dashboard.html', context)
    
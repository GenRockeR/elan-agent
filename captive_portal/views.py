from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.contrib.sites.models import get_current_site
from django.utils.translation import ugettext as _
from origin.captive_portal import GUEST_ACCESS_CONF_PATH, submit_guest_request, is_authz_pending
from origin.neuron import Synapse
from origin.authentication import pwd_authenticate
from origin.utils import get_ip4_address, ip4_to_mac
from origin import nac, session
import datetime

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



@requirePortalURL
def redirect2status(request):
    return redirect('status')

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



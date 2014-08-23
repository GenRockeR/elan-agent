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
from django import forms
from django.core.validators import validate_ipv4_address, validate_ipv6_address 
from origin.network import NetworkConfiguration
import time

ADMIN_SESSION_IDLE_TIMEOUT = 300 #seconds

def requirePortalURL(fn):
    '''
    View decorator to make sure url used is the one of the agent and not the target URL 
    '''
    def wrapper(request, *args, **kwargs):
        agent_ip = get_ip4_address('br0')['address']
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
    context = {'guest_access': guest_access_conf, 'web_authentication': web_authentication}
    
    return render(request, 'captive-portal/status.html', context)

@requirePortalURL
def login(request, context=None):
    if context is None:
        context = {}

    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip4_to_mac(clientIP)
    vlan_id = request.META['vlan_id']
    
    if nac.macAllowed(clientMAC, vlan_id):
        return redirect('status')

    
    guest_access = request.META['guest_access']
    guest_access_conf = Synapse().hget(GUEST_ACCESS_CONF_PATH, guest_access)
    web_authentication = request.META['web_authentication']
    default_context = { 
              'guest_access': guest_access_conf,
              'guest_access_pending': is_authz_pending(clientMAC, vlan_id),
              'web_authentication': web_authentication,
    }
    if guest_access_conf:
        default_context.update(guest_registration_fields = guest_access_conf['registration_fields'])

    for key in default_context:
        if key not in context:
            context[key] = default_context[key]
    
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


class DynamicFieldForm(forms.Form):
    FIELD_MAPPING = {
            'text': forms.CharField,
            'textarea': forms.CharField,
            'date': forms.DateField,
            'date-time': forms.DateTimeField,
            'time': forms.TimeField,
            'email': forms.EmailField,
    }
    def __init__(self, *args, **kwargs):
        fields = kwargs.pop('fields')
        super().__init__(*args, **kwargs)
        
        for field in fields:
            self.fields[field['name']] = self.FIELD_MAPPING[field['type']](required=field.get('required'))
            validation_patterns = field.get('validation_patterns', [])
            if validation_patterns:
                self.create_validator(field['name'], validation_patterns)
        
    def create_validator(self, name, patterns):
        import fnmatch
        def field_validator(form):
            value = form.cleaned_data[name]
            for pattern in patterns:
                if fnmatch.fnmatch(value, pattern):
                    return value
            raise forms.ValidationError(_("Field does not match one of the patterns ({})").format(', '.join(patterns)))
        setattr(self, 'clean_{}'.format(name), field_validator.__get__(self))

def get_request_form(guest_registration_fields, guest_access_conf, data=None):
    form_fields = [{'name':'field-{}'.format(f['id']), 'required':f.get('required', False), 'type':f.get('type')} for f in guest_registration_fields]
    if guest_access_conf['validation_patterns']:
        form_fields.append({'name':'sponsor_email', 'required':True, 'validation_patterns': guest_access_conf['validation_patterns'], 'type': 'email'})
    return DynamicFieldForm( data, fields=form_fields )

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
    
    form = get_request_form(guest_registration_fields, guest_access_conf, request.POST)
    
    request.POST
    
    if form.is_valid():
        guest_request = dict(mac=clientMAC, vlan=vlan, fields=[], sponsor_email=request.POST.get('sponsor_email', ''))
        for field in guest_registration_fields:
            guest_request['fields'].append( dict( 
                                         display_name=field['display_name'],
                                         type=field['type'],
                                         value=request.POST.get('field-{}'.format(field['id']), ''),
                                         position=field['position']
            ) )
        
        submit_guest_request(guest_request)
    
        return redirect('status')
    else:
        # we update the field conf with passed value and error messages as it is easier to display in Template (difficult to access error.var where var='field-{id}' and to build that access in the template)
        for field in guest_registration_fields:
            field.update( value = request.POST.get('field-{}'.format(field['id']), '') )
            field.update( errors = form.errors.get('field-{}'.format(field['id']), []) )
                
        context = {'guest_request_errors': form.errors, 'guest_registration_fields': guest_registration_fields, 'form': form }
        return login(request, context)


# Session function helpers
def admin_session_login(session, login):
    session['admin'] = login
    session.set_expiry(ADMIN_SESSION_IDLE_TIMEOUT)

def admin_session_logout(session):
    session.clear()
    session.flush()


def require_admin(fn):
    def wrapper(request, *args, **kwargs):
        if request.session.get('admin', None):
            return fn(request, *args, **kwargs)
        return redirect('dashboard')

    return wrapper

def require_post(fn):
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return redirect2status(request)
        return fn(request, *args, **kwargs)
    return wrapper


def save_admin_session(fn):
    def wrapper(request, *args, **kwargs):
        if request.session.get('admin', None):
            request.session.modified = True
        return fn(request, *args, **kwargs)
    return wrapper


@save_admin_session
def dashboard(request, context=None):
    if context is None:
        context={}
    context.update(
               is_connected = Axon.is_connected(),
               is_admin = bool(request.session.get('admin', False)),
               wan_up = is_iface_up('eth0'),
               lan_up = is_iface_up('eth1'),
               is_registered = Axon.is_registered(),

               ipsv4 = [utils.get_ip4_address('br0')],
               ipv4_gw = utils.get_ip4_default_gateway(),
               ipv4_dns = utils.get_ip4_dns_servers(),

               ipsv6 = utils.get_ip6_global_addresses('br0'),
               ipv6_gw = utils.get_ip6_default_gateway(),
               ipv6_dns = utils.get_ip6_dns_servers(),
    )
    if not context.get('location', ''):
        context['location'] = Axon.agent_location() or ''
    
    ip_conf = NetworkConfiguration()
    if not context.get('ipv4_form', None):
        context['ipv4_form'] = Ip4ConfigurationForm(initial=ip_conf.ipv4)
    if not context.get('ipv6_form', None):
        context['ipv6_form'] = Ip6ConfigurationForm(initial=ip_conf.ipv6)

    return render(request, 'captive-portal/dashboard.html', context)

def admin_logout(request):
    admin_session_logout(request.session)
    
    return redirect('dashboard')

@require_post
def admin_login(request):
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

class MultiIp4AddressField(forms.Field):
    def to_python(self, value):
        "Normalize data to a list of strings."

        # Return an empty list if no input was given.
        if not value:
            return []
        return value.replace(' ','').split(',')

    def validate(self, value):
        "Check if value consists only of valid IPv4s."

        # Use the parent's handling of required fields, etc.
        super(MultiIp4AddressField, self).validate(value)

        for ip in value:
            validate_ipv4_address(ip)

    def prepare_value(self, value):
        if isinstance(value, list):
            return ', '.join(value)
        return value

class Ip4ConfigurationForm(forms.Form):
    type = forms.CharField(required=True)
    address = forms.IPAddressField(required=False)
    mask = forms.IntegerField(required=False, min_value=0, max_value=32)
    gateway = forms.IPAddressField(required=False)
    dns = MultiIp4AddressField(required=False)

    def clean_address(self):
        data = self.cleaned_data
        address =  data.get('address', '')
        if data.get('type') == 'static' and not address:
            raise forms.ValidationError('Address is required for Static configuration')
        return address

    def clean_mask(self):
        data = self.cleaned_data
        mask =  data.get('mask', '')
        if data.get('type') == 'static' and not mask:
            raise forms.ValidationError('Mask is required for Static configuration')
        return mask

    def clean_gateway(self):
        data = self.cleaned_data
        gateway =  data.get('gateway', '')
        if data.get('type') == 'static' and not gateway:
            raise forms.ValidationError('Gateway is required for Static configuration')
        return gateway
        
class MultiIp6AddressField(forms.Field):
    def to_python(self, value):
        "Normalize data to a list of strings."
        # Return an empty list if no input was given.
        if not value:
            return []
        return value.replace(' ','').split(',')
    def validate(self, value):
        "Check if value consists only of valid IPv4s."
        # Use the parent's handling of required fields, etc.
        super(MultiIp6AddressField, self).validate(value)
        for ip in value:
            validate_ipv6_address(ip)
    def prepare_value(self, value):
        if isinstance(value, list):
            return ', '.join(value)
        return value

class Ip6ConfigurationForm(forms.Form):
    type = forms.CharField(required=True)
    address = forms.GenericIPAddressField(required=False, validators=[validate_ipv6_address])
    mask = forms.IntegerField(required=False, min_value=0, max_value=128)
    gateway = forms.GenericIPAddressField(required=False, validators=[validate_ipv6_address])
    dns = MultiIp6AddressField(required=False)

    def clean_address(self):
        data = self.cleaned_data
        address =  data.get('address', '')
        if data.get('type') == 'static' and not address:
            raise forms.ValidationError('Address is required for Static configuration')
        return address

    def clean_mask(self):
        data = self.cleaned_data
        mask =  data.get('mask', '')
        if data.get('type') == 'static' and not mask:
            raise forms.ValidationError('Mask is required for Static configuration')
        return mask

    def clean_gateway(self):
        data = self.cleaned_data
        gateway =  data.get('gateway', '')
        if data.get('type') == 'static' and not gateway:
            raise forms.ValidationError('Gateway is required for Static configuration')
        return gateway


@require_post
@require_admin
@save_admin_session
def admin_ipv4_conf(request):
    form = Ip4ConfigurationForm(request.POST)
    if form.is_valid():
        conf = NetworkConfiguration()
        conf.setIPv4Configuration(**form.cleaned_data)
        return redirect('dashboard')
    
    return dashboard(request, context={'ipv4_form': form})

@require_post
@require_admin
@save_admin_session
def admin_ipv6_conf(request):
    form = Ip6ConfigurationForm(request.POST)
    if form.is_valid():
        conf = NetworkConfiguration()
        conf.setIPv6Configuration(**form.cleaned_data)
        time.sleep(5) # wait for ipv6 autoconf
        return redirect('dashboard')
    
    return dashboard(request, context={'ipv6_form': form})
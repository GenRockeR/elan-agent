#! /usr/bin/env python3

import radiusd
from origin import neuron, snmp, session, nac
from origin.event import Event, InternalEvent, ExceptionEvent
import re, traceback

# TODO: maybe put this in instanciate ?
dendrite = neuron.Dendrite('freeradius')
synapse = dendrite.synapse
snmp_manager = snmp.DeviceSnmpManager() 

def extract_mac(string):
    # extract mac from beginning of string
    if not string:
        return
    
    m = re.match('([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})', string, flags=re.IGNORECASE)
    if m:
        return ':'.join(m.groups()).lower()

def extract_ssid(string):
    # extract mac from beginning of string
    if not string:
        return
    
    m = re.match('[a-f0-9]{2}[.:-]?[a-f0-9]{2}[.:-]?[a-f0-9]{2}[.:-]?[a-f0-9]{2}[.:-]?[a-f0-9]{2}[.:-]?[a-f0-9]{2}:(.+)', string, flags=re.IGNORECASE)
    if m:
        return m.group(1)

def seen(request):
    mac = extract_mac(request.get('Calling-Station-Id', None))

    port = find_port(request)
    session.seen(mac, port=port)

def end(request):
    mac = extract_mac(request.get('Calling-Station-Id', None))
    nac.macDisconnected(mac)


def find_port(request):
    # will try to find port 
    nas_ip_address = request.get('NAS-IP-Address', None)
    radius_client_ip = request.get('Packet-Src-IP-Address', request.get('Packet-Src-IPv6-Address', None))

    switch_polled = False
    switch = None

    # Retrieve switch info
    # first try nas_ip address in snmp cache then radius_client_ip
    # then try polling
    if nas_ip_address:
        switch = snmp_manager.get_device_by_ip(nas_ip_address)
    if switch:
        switch_ip = nas_ip_address
    else:
        switch = snmp_manager.get_device_by_ip(radius_client_ip)

    if switch:
        switch_ip = radius_client_ip
    else:
        # still not found try polling nas IP adddress, then ip the radius request came from
        switch_polled = True
        if nas_ip_address:
            switch = snmp_manager.poll(nas_ip_address)
        if switch:
            switch_ip = nas_ip_address
        else:
            # If not found with NAS-IP-Address, try with Radius client IP
            switch = snmp_manager.poll(radius_client_ip)
            if switch:
                switch_ip = radius_client_ip
            else:
                # if switch not found, nothing we can do
                return
    
    called_station_id = extract_mac(request.get('Called-Station-Id', None))
    found_ports_by_mac = set()
    if called_station_id:
        for port in switch[u'ports']:
            if port[u'mac'] == called_station_id:
                found_ports_by_mac.add(port[u'interface'])
        if len(found_ports_by_mac) == 1:
            port_interface = list(found_ports_by_mac)[0]
            return { 'local_id': str(switch[u'local_id']), 'interface': str(port_interface) } 

    # Try to find SSID
    ssid = None
    for k,v in request.items():
        if '-avpair' in k.lower():
            if not isinstance(v, list):
                v=[v]
            for val in v:
                if val.lower().startswith('ssid='):
                    ssid = val.partition('=')[2]
                    break
            if ssid:
                break
    if not ssid:
        # try from called Station ID
        ssid = extract_ssid(request.get('Called-Station-Id', None))

    found_ports_by_ssid = set()
    if ssid:
        for port in switch[u'ports']:
            for ssid_obj in port.get(u'ssids', []):
                if ssid_obj[u'ssid'] == ssid:
                    found_ports_by_ssid.add(port[u'interface'])
                    break
        if len(found_ports_by_ssid) == 1:
            port_interface = list(found_ports_by_ssid)[0]
            return { 'local_id': str(switch[u'local_id']), 'interface': str(port_interface) } 
        


    # try to find by nas port id
    nas_port_id = request.get('NAS-Port-ID', None)
    found_ports_by_nas_port_id = set()
    if nas_port_id:
        for port in switch[u'ports']:
            if nas_port_id in (port[u'interface'], port[u'name'], port[u'description']):
                found_ports_by_nas_port_id.add(port[u'interface'])
        if len(found_ports_by_nas_port_id) == 1:
            port_interface = list(found_ports_by_nas_port_id)[0]
            return { 'local_id': str(switch[u'local_id']), 'interface': str(port_interface) } 
    
    
    # If still, try nasport to ifindex
    nas_port = request.get('NAS-Port', None)
    found_ports_by_nas_port = set()
    if nas_port:
        ifIndexes = snmp_manager.nasPort2IfIndexes(switch_ip, nas_port)
        force_poll = not switch_polled # force poll if not already polled
        for if_index in ifIndexes:
            port = snmp_manager.getPortFromIndex(switch_ip, if_index, force_poll=force_poll, no_poll=(not force_poll))
            force_poll = False # Polled once, no need to poll any more
            if port:
                found_ports_by_nas_port.add(port['interface'])
        if len(found_ports_by_nas_port) == 1:
            port_interface = list(found_ports_by_nas_port)[0]
            return { 'local_id': str(switch[u'local_id']), 'interface': str(port_interface) }
        
    # TODO: Try to use forward mac table (fw_mac) to find on what port mac is on... (but do not save that to cache...)
    
    # try to find a common one between the 3
    intersection = found_ports_by_mac | found_ports_by_ssid | found_ports_by_nas_port_id | found_ports_by_nas_port
    if found_ports_by_mac:
        intersection &= found_ports_by_mac
    if found_ports_by_ssid:
        intersection &= found_ports_by_ssid
    if found_ports_by_nas_port_id:
        intersection &= found_ports_by_nas_port_id
    if found_ports_by_nas_port:
        intersection &= found_ports_by_nas_port
    if len(intersection) == 1:
        port_interface = intersection[0]
        return { 'local_id': str(switch[u'local_id']), 'interface': str(port_interface) }
    
    # port not found...
    InternalEvent(source='radius')\
        .add_data('module', 'origin.freeradius.mac')\
        .add_data('details', 'Port not found')\
        .add_data('request', request)\
        .add_data('switch', switch)\
        .notify()

    return { 'local_id': str(switch[u'local_id']), 'interface': None }

def request_as_hash_of_values(request):
    class MultiDict(dict):
        'Dictionary that returns only last value when get is used and value is a list'
        def get(self, *args, **kwargs):
            v = super(MultiDict, self).get(*args, **kwargs)
            if isinstance(v, list):
                return v[-1]
            return v
            
    ret = MultiDict()
    
    for key, value in request:
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if key in ret:
            if isinstance(ret[key], list):
                ret[key].append(value)
            else:
                ret[key] = [ ret[key], value ]
        else:
            ret[key] = value

    return ret


def get_assignments(request):
    ''' Will create new session for Mac and allow it on VLAN and on the net if authorized'''
    mac = extract_mac(request.get('Calling-Station-Id', None))

    port = find_port(request)

    session.seen(mac, port=port)

    auth_type = request.get('Origin-Auth-Type', None)
    
    extra_kwargs = {}
    if auth_type == 'mac':
        nac.checkAuthz(mac)
    elif auth_type == 'dot1x':
        authz = nac.newAuthz( mac, 
                              no_duplicate_source = True,
                              source = 'dot1x',
                              till_disconnect = True,
                              authentication_provider = request.get('Origin-Auth-Provider'),
                              login = request.get('Origin-Login', request.get('User-Name'))
                            )

    if not authz:
        # log no assignment rule matched....
        event = Event( event_type='device-not-authorized', source='radius-'+auth_type) 
        event.add_data('mac', mac, 'mac')
        event.add_data('port', port, 'port')
        if auth_type == 'dot1x':
            event.add_data('authentication_provider', extra_kwargs['authentication_provider'], 'authentication_provider')
            event.add_data('login', extra_kwargs['login'])
        event.notify()

        return radiusd.RLM_MODULE_REJECT
    
    return radiusd.RLM_MODULE_UPDATED, ( ('Origin-Vlan-Id', str(authz.vlan)), ), ()


def post_auth(req):
    try:
        request = request_as_hash_of_values(req)
        
        if request.get('Origin-Auth-Type', None) == 'Reject':
            return seen(request)
        else:
            return get_assignments(request)
    except:
        ExceptionEvent(source='radius').notify()
        raise

def accounting(req):
    try:
        request = request_as_hash_of_values(req)
        if request.get('Acct-Status-Type') == 'Stop':
            return end(request)
        elif request.get('Acct-Status-Type') in ['Start', 'Interim-Update']:
            return seen(request)
    except:
        ExceptionEvent(source='radius').notify()
        raise
            
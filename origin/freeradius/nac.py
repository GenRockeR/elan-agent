#! /usr/bin/env python3

import radiusd
from origin import nac, neuron, snmp, session
import re

# TODO: maybe put this in instanciate ?
synapse = neuron.Synapse()
snmp_manager = snmp.DeviceSnmpManager() 

def extract_mac(string):
    # extract mac from beginning of string
    if not string:
        return
    
    m = re.match('([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})[.:-]?([a-f0-9]{2})', string, flags=re.IGNORECASE)
    if m:
        return ':'.join(m.groups()).lower()
    
def find_port(request):
    request_hash = request_as_hash_of_values(request)

    nas_ip_address = request_hash.get('NAS-IP-Address', None)
    radius_client_ip = request_hash.get('Packet-Src-IP-Address', request_hash.get('Packet-Src-IPv6-Address', None))
    called_station_id = extract_mac(request_hash.get('Called-Station-Id', None))
    nas_port = request_hash.get('NAS-Port', None)
    nas_port_id = request_hash.get('NAS-Port-ID', None)

    # Retrieve switch info
    if nas_ip_address:
        switch = snmp_manager.get_device_by_ip(nas_ip_address)
        if not switch:
            switch = snmp_manager.poll(nas_ip_address)
    if not switch:
        switch = snmp_manager.get_device_by_ip(radius_client_ip)
        if not switch:
            switch = snmp_manager.poll(radius_client_ip)
    
    # if switch not found, nothing we can do
    if not switch:
        return
    
    if called_station_id:
        found_ports = []
        for port in switch[u'ports']:
            if port[u'mac'] == called_station_id:
                found_ports.append(port)
        if len(found_ports) == 1:
            port = found_ports[0]
            return radiusd.RLM_MODULE_UPDATED, ( ('ORIGIN-Switch-Id', str(switch[u'local_id'])), ('ORIGIN-Switch-Interface', str(port[u'interface'])),), () 
    # Todo: If still, try nasport to ifindex
    
    return radiusd.RLM_MODULE_NOTFOUND

def request_as_hash_of_values(request):
    ret = {}
    for key, value in request:
        if value.startswith('"') and value.endswith('"'):
            ret[key]= value[1:-1]
        else:
            ret[key]= value

    return ret

def seen(request):
    ''' Will create new session for Mac on Vlan and allow it on the network if authorized'''
    request_hash = request_as_hash_of_values(request)
    
    switch_id = request_hash.get('Origin-Switch-Id', None)
    switch_interface = request_hash.get('Origin-Switch-Interface', None)
    if switch_id:
        port = dict(local_id=switch_id, interface=switch_interface)
    else:
        port = None
        
    vlan = request_hash.get('ORIGIN-Vlan-Id', None)

    mac = extract_mac(request_hash.get('Calling-Station-Id', None))
    
    session.seen(mac=mac, port=port, vlan=vlan)
    
    # Notify new  authorization and allow to go to the net
    if request_hash.get('Origin-Authorized', False):
        auth_type = request_hash.get('Origin-Auth-Type', None)
        
        extra_kwargs = {}
        if auth_type == 'dot1x':
            extra_kwargs = dict(
                    authentication_provider = request_hash.get('Origin-Auth-Provider'),
                    login = request_hash.get('Origin-Login', request_hash.get('User-Name'))
            )
        
        session.notify_new_authorization_session(mac=mac, vlan=vlan, type=auth_type, **extra_kwargs)
        nac.allowMAC(mac=mac, vlan=vlan, disallow_mac_on_disconnect=True)
    
    return radiusd.RLM_MODULE_OK 
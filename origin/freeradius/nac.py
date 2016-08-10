#! /usr/bin/env python3

from .utils import request_as_hash_of_values
from origin import snmp, session, nac
from origin.event import Event, InternalEvent, ExceptionEvent
import re
import asyncio
import functools

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

async def seen(request):
    mac = extract_mac(request.get('Calling-Station-Id', None))

    port = await find_port(request)
    await asyncio.get_event_loop().run_in_executor(None, functools.partial(session.seen, mac, port=port))

async def end(request):
    mac = extract_mac(request.get('Calling-Station-Id', None))
    await asyncio.get_event_loop().run_in_executor(None, session.end, mac)


async def find_port(request):
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
            switch = await snmp_manager.poll(nas_ip_address)
        if switch:
            switch_ip = nas_ip_address
        else:
            # If not found with NAS-IP-Address, try with Radius client IP
            switch = await snmp_manager.poll(radius_client_ip)
            if switch:
                switch_ip = radius_client_ip
            else:
                # if switch not found, nothing we can do
                return
    
    result = {}
    
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
    if ssid:
        result['ssid'] = ssid

    found_ports = {} # by method (mac, ssid, nas_port_id, etc....)
    
    called_station_id = extract_mac(request.get('Called-Station-Id', None))
    found_ports['mac'] = set()
    if called_station_id:
        for port in switch[u'ports']:
            if port[u'mac'] == called_station_id:
                found_ports['mac'].add(port[u'interface'])
        if len(found_ports['mac']) == 1:
            port_interface = list(found_ports['mac'])[0]
            result.update(local_id=str(switch[u'local_id']), interface=str(port_interface) )
            return result 

    found_ports['ssid'] = set()
    if ssid:
        for port in switch[u'ports']:
            for ssid_obj in port.get(u'ssids', []):
                if ssid_obj[u'ssid'] == ssid:
                    found_ports['ssid'].add(port[u'interface'])
                    break
        if len(found_ports['ssid']) == 1:
            result.update(local_id=str(switch[u'local_id']), interface=str(port_interface) )
            return result 
        


    # try to find by nas port id
    nas_port_id = request.get('NAS-Port-ID', None)
    found_ports['nas_port_id'] = set()
    if nas_port_id:
        for port in switch[u'ports']:
            if nas_port_id in (port[u'interface'], port[u'name'], port[u'description']):
                found_ports['nas_port_id'].add(port[u'interface'])
        if len(found_ports['nas_port_id']) == 1:
            port_interface = list(found_ports['nas_port_id'])[0]
            result.update(local_id=str(switch[u'local_id']), interface=str(port_interface) )
            return result 
    
    
    # If still not found, try nasport to ifindex
    nas_port = request.get('NAS-Port', None)
    found_ports['nas_port'] = set()
    if nas_port:
        ifIndexes = await snmp_manager.nasPort2IfIndexes(switch_ip, nas_port)
        for if_index in ifIndexes:
            force_poll = not switch_polled # force poll if not already polled
            port = await snmp_manager.getPortFromIndex(switch_ip, if_index, force_poll=force_poll, no_poll=(not force_poll))
            switch_polled = True
            if port:
                found_ports['nas_port'].add(port['interface'])
        if len(found_ports['nas_port']) == 1:
            port_interface = list(found_ports['nas_port'])[0]
            result.update(local_id=str(switch[u'local_id']), interface=str(port_interface) )
            return result 
        
    # TODO: Try to use forward mac table (fw_mac) to find on what port mac is on... ( save that to cache but do not notify CC at each change....)
#     if switch_polled:
#         switch = snmp_manager.get_device_by_ip(switch_ip) # may have been polled after switch was retrieved
#     else:
#         switch = snmp_manager.poll(switch_ip)
#     if switch:
#         # find port
        
    
    # try to find a common one between all methods
    intersection = set()
    for method in found_ports:
        intersection |= found_ports[method]
    for method in found_ports:
        if found_ports[method]:
            intersection &= found_ports[method]
    if len(intersection) == 1:
        port_interface = intersection[0]
        result.update(local_id=str(switch[u'local_id']), interface=str(port_interface) )
        return result 
    
    # port not found...
    InternalEvent(source='radius')\
        .add_data('module', 'origin.freeradius.mac')\
        .add_data('details', 'Port not found')\
        .add_data('request', request)\
        .add_data('switch', switch)\
        .add_data('found_ports', { k: list(v) for k,v in found_ports.items() })\
        .notify()
        # sets are not JSON serializable

    result.update(local_id=str(switch[u'local_id']), interface=None )
    return result 


class NotAuthorized(Exception):
    pass

async def get_assignments(request):
    ''' Will create new session for Mac and allow it on VLAN and on the net if authorized'''
    mac = extract_mac(request.get('Calling-Station-Id', None))

    port = await find_port(request)

    session.seen(mac, port=port)

    auth_type = request.get('Origin-Auth-Type', None)
    
    if auth_type == 'radius-mac':
        authz = await asyncio.get_event_loop().run_in_executor(None, nac.checkAuthz, mac)
    elif auth_type == 'radius-dot1x':
        authentication_provider = request.get('Origin-Auth-Provider')
        login = request.get('Origin-Login', request.get('User-Name'))
        authz = await asyncio.get_event_loop().run_in_executor(None, functools.partial(
                                nac.newAuthz,
                                mac, 
                                no_duplicate_source = True,
                                source = 'radius-dot1x',
                                till_disconnect = True,
                                authentication_provider = authentication_provider,
                                login = login
                            )
        )

    if not authz:
        # log no assignment rule matched....
        event = Event( event_type='device-not-authorized', source=auth_type, level='warning') 
        event.add_data('mac', mac, 'mac')
        event.add_data('port', port, 'port')
        if auth_type == 'radius-dot1x':
            event.add_data('authentication_provider', authentication_provider, 'authentication')
            event.add_data('login', login)
        event.notify()

        raise NotAuthorized
    
    return {'Origin-Vlan-Id': str(authz.assign_vlan)}


async def post_auth(req):
    try:
        request = request_as_hash_of_values(req)
        
        if request.get('Origin-Auth-Type', None) == 'Reject':
            return await seen(request)
        else:
            return await get_assignments(request)
    except:
        ExceptionEvent(source='radius').notify()
        raise

async def accounting(req):
    try:
        request = request_as_hash_of_values(req)
        if request.get('Acct-Status-Type') in ('Stop', 2):
            return await end(request)
        elif request.get('Acct-Status-Type') in ('Start', 1, 'Interim-Update', 3):
            return await seen(request)
    except:
        ExceptionEvent(source='radius').notify()
        raise
            

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
import subprocess, re
from django.views.decorators.cache import never_cache
from django.contrib.sites.models import get_current_site
import socket
import fcntl
import struct
import pyrad.packet
from pyrad.client import Client
from pyrad.dictionary import Dictionary

def requirePortalURL(fn):
    '''
    View decorator to make sure url used is the one of the agent and not the target URL 
    '''
    def wrapper(request, *args, **kwargs):
        agent_ip = get_ip_address('br0')
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
    clientMAC = ip2mac(clientIP)
    if not macAllowed(clientMAC):
        return redirect('login')
    return HttpResponse('U R now connected !: ' + request.build_absolute_uri() + " -- " + str(get_current_site(request)) + " -- ")

@requirePortalURL
def login(request):
    if request.method == 'POST':
        try:
            username = request.POST['username']
            password = request.POST['password']
        except (KeyError):
            # Redisplay the login form.
            return render(request, 'captive_portal/login.html', { 'error_message': "'username' or 'password' missing.",})
        if not authenticate(request.authenticator_id, username, password):
            return render(request, 'captive_portal/login.html', { 'error_message': "Invalid username or password.", 'username': username})
    
        clientIP = request.META['REMOTE_ADDR']
        clientMAC = ip2mac(clientIP)
        allowMAC(clientMAC)
        return redirect('status')

    return render(request, 'captive_portal/login.html')

@requirePortalURL
def logout(request):
    clientIP = request.META['REMOTE_ADDR']
    clientMAC = ip2mac(clientIP)
    disallowMAC(clientMAC)
    #TODO: Flush connections with conntrack (get IPs of MAC and conntrack -D -s <IP>)
    
    return redirect('login')

def authenticate(authenticator_id, user, pwd):
    srv = Client(server="127.0.0.1", authport=18122, secret="a2e4t6u8qmlskdvcbxnw",
                 dict=Dictionary("/origin/captive-portal/radius/dictionary"))
    
    req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,
              User_Name=user, Connect_Info='authenticator={}'.format(authenticator_id) )
    req["User-Password"]=req.PwCrypt(pwd)
    
    reply = srv.SendPacket(req)
    
    return reply.code == pyrad.packet.AccessAccept

# Temp Hack
def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])
    
def ip2mac(ip):
    p = subprocess.Popen(['ip','neigh', 'show', ip], stdout=subprocess.PIPE)
    output = p.communicate()[0]
    m = re.search(r'[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]', output)
    if m:
        return str(m.group(0))

def macAllowed(mac):
    return subprocess.call('sudo ebtables -t nat -L PREROUTING --Lx --Lmac2 | grep -qi {mac}'.format(mac=mac), shell=True) == 0

def allowMAC(mac):
    if not macAllowed(mac):
        subprocess.call('sudo ebtables -t nat -I PREROUTING -s {mac} -j mark --mark-set 0x9'.format(mac=mac), shell=True)

def disallowMAC(mac):
    if macAllowed(mac):
        subprocess.call('sudo ebtables -t nat -D PREROUTING -s {mac} -j mark --mark-set 0x9'.format(mac=mac), shell=True)


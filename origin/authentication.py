import pyrad.packet
from pyrad.client import Client
from pyrad.dictionary import Dictionary


def pwd_authenticate(authenticator_id, user, pwd):
    srv = Client(server="127.0.0.1", authport=18122, secret="a2e4t6u8qmlskdvcbxnw",
                 dict=Dictionary("/origin/captive-portal/radius/dictionary"))
    
    req = srv.CreateAuthPacket(code=pyrad.packet.AccessRequest,
              User_Name=user, Connect_Info='authenticator={}'.format(authenticator_id) )
    req["User-Password"]=req.PwCrypt(pwd)
    
    reply = srv.SendPacket(req)
    
    return reply.code == pyrad.packet.AccessAccept

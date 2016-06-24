import unittest

import sys
sys.path.insert(0, "exec")

import connection_trackerd

class IgnorePacket(unittest.TestCase):
    def test_ignorePacket_broadcast_OK(self):
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': 'ff:ff:ff:ff:ff:01' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == False )
    
    def test_ignorePacket_broadcast(self):
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': 'ff:ff:ff:ff:ff:ff' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == True )
        assert( connection_trackerd.ignorePacket({'dst' : { 'mac': 'ff:ff:ff:ff:ff:ff' }, 'src' : { 'mac': '01:02:03:04:05:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': 'ff:ff:ff:ff:ff:ff' }, 'dst' : { 'mac': 'ff:ff:ff:ff:ff:ff'}}) == True )
    
    def test_ignorePacket_IANA(self):
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '00:00:5e:05:06:07' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == True )
        assert( connection_trackerd.ignorePacket({'dst' : { 'mac': '00:00:5e:05:06:07' }, 'src' : { 'mac': '01:02:03:04:05:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '00:00:5e:05:06:07' }, 'dst' : { 'mac': '00:00:5e:05:06:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '01:00:5e:05:06:07' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == True )
        assert( connection_trackerd.ignorePacket({'dst' : { 'mac': '01:00:5e:05:06:07' }, 'src' : { 'mac': '01:02:03:04:05:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '01:00:5e:05:06:07' }, 'dst' : { 'mac': '01:00:5e:05:06:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '02:00:5e:05:06:07' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == True )
        assert( connection_trackerd.ignorePacket({'dst' : { 'mac': '02:00:5e:05:06:07' }, 'src' : { 'mac': '01:02:03:04:05:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '02:00:5e:05:06:07' }, 'dst' : { 'mac': '02:00:5e:05:06:07'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': '33:33:ff:ff:ff:01' }, 'dst' : { 'mac': '01:02:03:04:05:06'}}) == True )
        assert( connection_trackerd.ignorePacket({'src' : { 'mac': 'ff:ff:ff:ff:ff:01' }, 'dst' : { 'mac': '33:33:03:04:05:06'}}) == True )

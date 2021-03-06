from unittest import mock
import unittest

from elan import session


def clear_redis_session_info():
    paths = [
        session.LAST_SEEN_PATH, session.SESSION_IDS_PATH, session.MAC_PORT_PATH, session.MAC_LAST_PORT_PATH,
        *session.synapse.keys(session.MAC_VLANS_PATH.format(mac='*', vlan='*', ip='*')),
        *session.synapse.keys(session.MAC_VLAN_IPS_PATH.format(mac='*', vlan='*')),
        *session.synapse.keys(session.MAC_AUTH_SESSION_PATH.format(mac='*'))
    ]
    for path in paths:
        session.synapse.delete(path)


class SessionTest(unittest.TestCase):

    def setUp(self):
        clear_redis_session_info()

    @mock.patch('elan.session.notify_MAC_port', wraps=session.notify_MAC_port)
    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_new_mac(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session, notify_MAC_port):
        response = session.seen(mac='aa:bb:cc:dd:ee:01')

        self.assertEqual(response, (True, False, False))
        self.assertEqual(notify_new_MAC_session.call_count, 1)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertEqual(notify_MAC_port.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))

    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_known_mac(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        session.seen(mac='aa:bb:cc:dd:ee:01')
        notify_new_MAC_session.reset_mock()

        response = session.seen(mac='aa:bb:cc:dd:ee:01')

        self.assertEqual(response, (False, False, False))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))

    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_new_mac_new_vlan(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1')

        self.assertEqual(response, (True, True, False))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 1)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))

        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1')
        self.assertEqual(response, (False, False, False))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 1)  # Not changed
        self.assertEqual(notify_new_IP_session.call_count, 0)

    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_known_mac_new_vlan(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        session.seen(mac='aa:bb:cc:dd:ee:01')
        notify_new_MAC_session.reset_mock()

        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1')

        self.assertEqual(response, (False, True, False))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 1)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))

    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_new_mac_new_vlan_new_ip(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4')

        self.assertEqual(response, (True, True, True))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 1)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4'))

        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4')

        self.assertEqual(response, (False, False, False))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 1)  # Not changed

    @mock.patch('elan.session.notify_new_IP_session', wraps=session.notify_new_IP_session)
    @mock.patch('elan.session.notify_new_VLAN_session', wraps=session.notify_new_VLAN_session)
    @mock.patch('elan.session.notify_new_MAC_session', wraps=session.notify_new_MAC_session)
    def test_seen_known_mac_known_vlan_new_ip(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1')
        notify_new_VLAN_session.reset_mock()

        response = session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4')

        self.assertEqual(response, (False, False, True))
        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 1)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))

    @mock.patch('elan.session.notify_end_MAC_session', wraps=session.notify_end_MAC_session)
    @mock.patch('elan.session.notify_MAC_port', wraps=session.notify_MAC_port)
    def test_seen_with_port(self, notify_MAC_port, notify_end_MAC_session):
        self.assertIsNone(session.mac_port('aa:bb:cc:dd:ee:01'))

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': 'i1'})

        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i1'})
        self.assertEqual(notify_MAC_port.call_count, 0)
        self.assertEqual(notify_end_MAC_session.call_count, 0, 'No session end on same port')

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': 'i2'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i2'})
        self.assertEqual(notify_MAC_port.call_count, 0)
        self.assertEqual(notify_end_MAC_session.call_count, 1, 'session ended on change of port')

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': None})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i2'})
        self.assertEqual(notify_MAC_port.call_count, 0)
        self.assertEqual(notify_end_MAC_session.call_count, 1, 'Session end on port change')

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':2, 'interface': None, 'ssid': 'SSID'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':2, 'interface': None, 'ssid': 'SSID'})
        self.assertEqual(notify_MAC_port.call_count, 0)
        self.assertEqual(notify_end_MAC_session.call_count, 2, 'No session end on same port')

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':2, 'interface': 'i3'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':2, 'interface': 'i3', 'ssid': 'SSID'})
        self.assertEqual(notify_MAC_port.call_count, 1)
        self.assertEqual(notify_end_MAC_session.call_count, 2, 'No session end on same port')

    @mock.patch('elan.session.notify_end_MAC_session', wraps=session.notify_end_MAC_session)
    @mock.patch('elan.session.notify_end_VLAN_session', wraps=session.notify_end_VLAN_session)
    @mock.patch('elan.session.notify_end_IP_session', wraps=session.notify_end_IP_session)
    def test_end(self, notify_end_IP_session, notify_end_VLAN_session, notify_end_MAC_session):
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2', ip='1.2.3.2')
        session.seen(mac='aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3')

        session.end(mac='aa:bb:cc:dd:ee:01')

        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))
        self.assertEqual(notify_end_MAC_session.call_count, 1)

        session.end(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2')

        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:02'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:02', vlan='eth0.2'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:02', vlan='eth0.2', ip='1.2.3.2'))
        self.assertEqual(notify_end_VLAN_session.call_count, 1)

        session.end(mac='aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3')

        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:03'))
        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:03', vlan='eth0.3'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3'))
        self.assertEqual(notify_end_IP_session.call_count, 1)

    def test_authentication_sessions_till_disconnect(self):
        mac = 'aa:bb:cc:dd:ee:01'
        session.seen(mac=mac, vlan='eth0.1', ip='1.2.3.1')
        session.add_authentication_session(mac, source='test')

        self.assertTrue(session.source_in_authentication_sessions(mac, 'test'))
        self.assertEqual(session.get_authentication_sessions(mac), [{'till_disconnect': True, 'source': 'test'}])
        self.assertEqual(session.get_authentication_sessions(mac, source='test'), [{'till_disconnect': True, 'source': 'test'}])
        self.assertEqual(session.get_authentication_sessions(mac, till_disconnect=False), [])

        session.end(mac)

        self.assertFalse(session.source_in_authentication_sessions(mac, 'test'))
        self.assertEqual(session.get_authentication_sessions(mac), [])


class SessionInternalsTest(unittest.TestCase):

    def setUp(self):
        clear_redis_session_info()

    def test_session_ids_field(self):
        self.assertEqual(session.session_ids_field('aa:bb:cc:dd:ee:01'), 'mac=aa:bb:cc:dd:ee:01')
        self.assertEqual(session.session_ids_field('aa:bb:cc:dd:ee:01', 'eth0.1'), 'mac=aa:bb:cc:dd:ee:01,vlan=eth0.1')
        self.assertEqual(session.session_ids_field('aa:bb:cc:dd:ee:01', 'eth0.1', '1.2.3.4'), 'mac=aa:bb:cc:dd:ee:01,vlan=eth0.1,ip=1.2.3.4')

    def test_field_to_mac_vlan_ip(self):
        self.assertEqual(session.field_to_mac_vlan_ip('mac=aa:bb:cc:dd:ee:01'), ('aa:bb:cc:dd:ee:01', None, None))
        self.assertEqual(session.field_to_mac_vlan_ip('mac=aa:bb:cc:dd:ee:01,vlan=eth0.1'), ('aa:bb:cc:dd:ee:01', 'eth0.1', None))
        self.assertEqual(session.field_to_mac_vlan_ip('mac=aa:bb:cc:dd:ee:01,vlan=eth0.1,ip=1.2.3.4') , ('aa:bb:cc:dd:ee:01', 'eth0.1', '1.2.3.4'))

    def test_get_current_session_ids(self):
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4')
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.5')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.1')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2')
        session.seen(mac='aa:bb:cc:dd:ee:03')

        session_ids = session.get_current_session_ids()

        self.assertEqual(set(session_ids.keys()), {
            ('aa:bb:cc:dd:ee:01', 'eth0.1', '1.2.3.4'),
            ('aa:bb:cc:dd:ee:01', 'eth0.1', '1.2.3.5'),
            ('aa:bb:cc:dd:ee:01', 'eth0.1', None),
            ('aa:bb:cc:dd:ee:02', 'eth0.1', None),
            ('aa:bb:cc:dd:ee:02', 'eth0.2', None),
            ('aa:bb:cc:dd:ee:01', None, None),
            ('aa:bb:cc:dd:ee:02', None, None),
            ('aa:bb:cc:dd:ee:03', None, None),
        })

    def test_notify_current_sessions(self):
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.4')
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.5')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.1')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2')
        session.seen(mac='aa:bb:cc:dd:ee:02')
        session.seen(mac='aa:bb:cc:dd:ee:03')

        self.assertEqual(session.notify_current_sessions(), 5)

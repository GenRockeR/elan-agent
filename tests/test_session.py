from unittest import mock
import unittest

from origin import session
from origin.session import notify_new_VLAN_session


class SessionTest(unittest.TestCase):

    def setUp(self):
        paths = [
            session.LAST_SEEN_PATH, session.SESSION_IDS_PATH, session.MAC_PORT_PATH, session.MAC_LAST_PORT_PATH,
            *session.synapse.keys(session.MAC_VLANS_PATH.format(mac='*', vlan='*', ip='*')),
            *session.synapse.keys(session.MAC_VLAN_IPS_PATH.format(mac='*', vlan='*')),
            *session.synapse.keys(session.MAC_AUTH_SESSION_PATH.format(mac='*'))
        ]
        for path in paths:
            session.synapse.delete(path)

    @mock.patch('origin.session.notify_new_IP_session')
    @mock.patch('origin.session.notify_new_VLAN_session')
    @mock.patch('origin.session.notify_new_MAC_session')
    def test_seen(self, notify_new_MAC_session, notify_new_VLAN_session, notify_new_IP_session):
        self.assertFalse(session.is_online(mac='aa:bb:cc:dd:ee:01'))

        self.assertEqual(session.seen(mac='aa:bb:cc:dd:ee:01'), (True, False, False))

        self.assertEqual(notify_new_MAC_session.call_count, 1)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertFalse(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertFalse(session.is_online(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2'))

        notify_new_MAC_session.reset_mock()
        notify_new_VLAN_session.reset_mock()
        notify_new_IP_session.reset_mock()

        self.assertEqual(session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'), (False, True, False))
        self.assertEqual(session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2'), (True, True, False))

        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 2)
        self.assertEqual(notify_new_IP_session.call_count, 0)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:02'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2'))
        self.assertFalse(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))
        self.assertFalse(session.is_online(mac='aa:bb:cc:dd:ee:03', vlan='eth0.2', ip='1.2.3.2'))
        self.assertFalse(session.mac_has_ip_on_vlan(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))

        notify_new_MAC_session.reset_mock()
        notify_new_VLAN_session.reset_mock()
        notify_new_IP_session.reset_mock()

        self.assertEqual(session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'), (False, False, True))
        self.assertEqual(session.seen(mac='aa:bb:cc:dd:ee:03', vlan='eth0.2', ip='1.2.3.2'), (True, True, True))

        self.assertEqual(notify_new_MAC_session.call_count, 0)
        self.assertEqual(notify_new_VLAN_session.call_count, 0)
        self.assertEqual(notify_new_IP_session.call_count, 2)
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:02'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))
        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:03', vlan='eth0.2', ip='1.2.3.2'))
        self.assertTrue(session.mac_has_ip_on_vlan(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))

    def test_seen_with_port(self):
        self.assertIsNone(session.mac_port('aa:bb:cc:dd:ee:01'))

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': 'i1'})

        self.assertTrue(session.is_online(mac='aa:bb:cc:dd:ee:01'))
        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i1'})

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': 'i2'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i2'})

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':1, 'interface': None})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':1, 'interface': 'i2'})

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':2, 'interface': None, 'ssid': 'SSID'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':2, 'interface': None, 'ssid': 'SSID'})

        session.seen(mac='aa:bb:cc:dd:ee:01', port={'local_id':2, 'interface': 'i3'})

        self.assertEqual(session.mac_port('aa:bb:cc:dd:ee:01'), {'local_id':2, 'interface': 'i3', 'ssid': 'SSID'})

    def test_end(self):
        session.seen(mac='aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1')
        session.seen(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2', ip='1.2.3.2')
        session.seen(mac='aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3')

        session.end(mac='aa:bb:cc:dd:ee:01')

        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01', vlan='eth0.1'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:01', vlan='eth0.1', ip='1.2.3.1'))

        session.end(mac='aa:bb:cc:dd:ee:02', vlan='eth0.2')

        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:02'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:02', vlan='eth0.2'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:02', vlan='eth0.2', ip='1.2.3.2'))

        session.end(mac='aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3')

        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:03'))
        self.assertTrue(session.is_online('aa:bb:cc:dd:ee:03', vlan='eth0.3'))
        self.assertFalse(session.is_online('aa:bb:cc:dd:ee:03', vlan='eth0.3', ip='1.2.3.3'))

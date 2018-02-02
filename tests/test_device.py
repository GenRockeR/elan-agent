from unittest import mock
import unittest

from elan import device


def clear_redis_session_info():
    paths = [
        *device.synapse.keys(device.MAC_HOSTNAME_PATH.format(mac='*', source='*')),
        *device.synapse.keys(device.MAC_FINGERPRINT_PATH.format(mac='*', source='*')),
    ]
    for path in paths:
        device.synapse.delete(path)


class DeviceTest(unittest.TestCase):

    def setUp(self):
        clear_redis_session_info()

    @mock.patch('elan.device.notify_fingerprint', wraps=device.notify_fingerprint)
    def test_seen_fingerprint(self, notify_fingerprint):
        response = device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 1}, source='source1')

        self.assertTrue(response)
        self.assertEqual(notify_fingerprint.call_count, 1, 'new notification')

        response = device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source1')

        self.assertTrue(response)
        self.assertEqual(notify_fingerprint.call_count, 2, 'new notification')

        response = device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source1')

        self.assertFalse(response)
        self.assertEqual(notify_fingerprint.call_count, 2, 'no notification')

        response = device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source2')

        self.assertTrue(response)
        self.assertEqual(notify_fingerprint.call_count, 3, 'new notification')

    def test_notify_known_fingerprints(self):
        device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 1}, source='source1')
        device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source1')
        device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source1')
        device.seen_fingerprint(mac='aa:bb:cc:dd:ee:01', fingerprint={'test': 2}, source='source2')
        device.seen_fingerprint(mac='aa:bb:cc:dd:ee:02', fingerprint={'test': 2}, source='source2')

        self.assertEqual(device.notify_known_fingerprints(), 3)

    @mock.patch('elan.device.notify_hostname', wraps=device.notify_hostname)
    def test_seen_hostname(self, notify_hostname):
        response = device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test1', source='source1')

        self.assertTrue(response)
        self.assertEqual(notify_hostname.call_count, 1, 'new notification')

        response = device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source1')

        self.assertTrue(response)
        self.assertEqual(notify_hostname.call_count, 2, 'new notification')

        response = device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source1')

        self.assertFalse(response)
        self.assertEqual(notify_hostname.call_count, 2, 'no notification')

        response = device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source2')

        self.assertTrue(response)
        self.assertEqual(notify_hostname.call_count, 3, 'new notification')

    def test_notify_known_hostnames(self):
        device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test1', source='source1')
        device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source1')
        device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source1')
        device.seen_hostname(mac='aa:bb:cc:dd:ee:01', hostname='test2', source='source2')
        device.seen_hostname(mac='aa:bb:cc:dd:ee:03', hostname='test3', source='source2')

        self.assertEqual(device.notify_known_hostnames(), 3)


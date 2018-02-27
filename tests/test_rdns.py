import unittest

from elan import rdns


def clear_redis_rdns_info():
    paths = [
        *rdns.synapse.keys(rdns.RDNS_PATH.format(mac='*', source='*')),
    ]
    for path in paths:
        rdns.synapse.delete(path)


class RdnsTest(unittest.TestCase):

    def setUp(self):
        clear_redis_rdns_info()

    def test_single(self):
        rdns.add_entries(
            dict(mac='mac1', source='1.2.3.4', rdns='fqdn1', ttl=5),
            dict(mac='mac2', source='1.2.3.4', rdns='fqdn2', ttl=6),
        )

        self.assertEqual(rdns.get_cached_rdns('1.2.3.4', 'mac1'), 'fqdn1')
        self.assertEqual(rdns.get_cached_rdns('1.2.3.4', 'mac2'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('1.2.3.4', 'mac3'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('1.2.3.4'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('4.4.4.4'), None)

    def test_with_cname(self):
        rdns.add_entries(
            dict(mac='mac1', source='1.2.3.4', rdns='fqdn1', ttl=5),
            dict(mac='mac1', source='fqdn1', rdns='fqdn2', ttl=6),
        )

        self.assertEqual(rdns.get_cached_rdns('1.2.3.4', 'mac1'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('1.2.3.4', 'mac2'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('1.2.3.4'), 'fqdn2')
        self.assertEqual(rdns.get_cached_rdns('4.4.4.4'), None)

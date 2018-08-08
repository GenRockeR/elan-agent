from unittest import mock
import unittest

from elan import network


class SessionTest(unittest.TestCase):

    @mock.patch('elan.network.open', new_callable=mock.mock_open)
    @mock.patch('elan.network.NetworkConfigurator.vlans_conf_template', 'netplan-vlans.yaml')
    def test_generate_default_vlans_conf(self, mock_file):
        network.NetworkConfigurator.generate_vlans_conf_files([{'interface': 'dummy1'}, {'interface': 'dummy2'}])

        handle = mock_file()
        handle.write.assert_called_once()
        self.assertNotIn('vlans', handle.write.call_args[0][0])

    @mock.patch('elan.network.open', new_callable=mock.mock_open)
    @mock.patch('elan.network.NetworkConfigurator.vlans_conf_template', 'netplan-vlans.yaml')
    def test_generate_vlans_conf(self, mock_file):
        network.NetworkConfigurator.generate_vlans_conf_files([{'interface': 'dummy1'}, {'interface': 'dummy2', 'vlan_id': 5}])

        handle = mock_file()
        handle.write.assert_called_once()
        self.assertEqual(handle.write.call_args[0][0].count('vlans:'), 1)

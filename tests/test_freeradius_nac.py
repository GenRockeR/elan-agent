from unittest.mock import MagicMock
import unittest

from origin.freeradius import nac
from origin.neuron import Dendrite


class UtilsTest(unittest.TestCase):

    def test_extract_mac(self):
        self.assertEqual(nac.extract_mac(''), None)
        self.assertEqual(nac.extract_mac('aa:bb:cc:dd:ee:ff'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AA:BB:CC:DD:EE:FF'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AABBCCDDEEFF'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AABBCC-DDEEFF'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AA.BB.CC.DD.EE.FF'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AA-BB-CC-DD-EE-FF'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('AA-BB-CC-DD-EE-FF:whatever'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(nac.extract_mac('qsqsAA-BB-CC-DD-EE-FFssdac'), None)

    def test_extract_ssid(self):
        self.assertEqual(nac.extract_ssid(''), None)
        self.assertEqual(nac.extract_ssid('aa:bb:cc:dd:ee:ff:ssid'), 'ssid')
        self.assertEqual(nac.extract_ssid('aabbcc-ddeeff:ssid'), 'ssid')
        self.assertEqual(nac.extract_ssid('crap:ssid'), None)

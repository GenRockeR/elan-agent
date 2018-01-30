import unittest

from elan.freeradius import utils


class UtilsTest(unittest.TestCase):

    def test_request_as_hash_of_values(self):
        values = utils.request_as_hash_of_values({
                'key1': dict(value='value1'),
                'key2': dict(value=['value2.1', 'value2.2'])
        })

        self.assertEqual(
            values,
            {'key1': 'value1', 'key2': ['value2.1', 'value2.2']}
        )

        self.assertEqual(values.get('key1'), 'value1')
        self.assertEqual(values.get('key2'), 'value2.2')

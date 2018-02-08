import glob
import os

from pyshark.capture.capture import Capture as PySharkCapture


class Capture(PySharkCapture):
    """
    Extend pyshark capture to use ring buffer (current version 02/2018 not working) with some better defaults for us.
    pyshark.LiveCapture does not send packets straight away, leading on small network to delay processing of such packets
    which can lead to some timeouts like device being marked offline while still on the network.
    Requires a name for the capture that will be used for naming the ring files.
    """

    def __init__(self, name, interface, ring_file_size=10240, num_ring_files=4, ring_file_folder='/tmp', **kwargs):
        super().__init__(**kwargs)

        if isinstance(interface, str):
            self.interfaces = [interface]
        else:
            self.interfaces = interface

        self.interfaces = interface
        self.ring_file_size = ring_file_size
        self.num_ring_files = num_ring_files
        self.ring_file_name = '{dir}/{name}.pcap'.format(dir=ring_file_folder, name=name)
        self.ring_file_pattern = '{dir}/{name}*.pcap'.format(dir=ring_file_folder, name=name)

    def get_parameters(self, packet_count=None):
        """
        Returns the special tshark parameters to be used according to the configuration of this class.
        """
        params = super().get_parameters(packet_count)
        params += [
                '-b', 'filesize:{size}'.format(size=self.ring_file_size),
                '-b', 'files:{nb}'.format(nb=self.num_ring_files),
                '-w', self.ring_file_name
        ]
        for interface in self.interfaces:
            params += ['-i', interface]

        return params

    def remove_files(self):
        for f in glob.glob(self.ring_file_pattern):
            os.remove(f)


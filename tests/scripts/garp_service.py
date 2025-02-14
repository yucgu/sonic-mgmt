import argparse
import json
import ptf
import ptf.testutils as testutils
import time

from ipaddress import ip_interface
from scapy.all import conf, Ether, IPv6, ICMPv6ND_NA, ICMPv6NDOptSrcLLAddr
from scapy.arch import get_if_hwaddr

class GarpService:

    def __init__(self, garp_config_file, interval):
        self.garp_config_file = garp_config_file
        self.interval = interval
        self.packets = {}
        self.dataplane = ptf.dataplane_instance

    def gen_garp_packets(self):
        '''
        Read the config file and generate a GARP packet for each configured interface
        '''

        with open(self.garp_config_file) as f:
            garp_config = json.load(f)

        for port, config in list(garp_config.items()):
            intf_name = 'eth{}'.format(port)
            source_mac = get_if_hwaddr(intf_name)
            source_ip_str = config['target_ip']
            source_ipv6_str = config['target_ipv6']
            dut_mac = config['dut_mac']
            dst_ipv6 = config['dst_ipv6']
            source_ip = str(ip_interface(source_ip_str).ip)
            source_ipv6 = str(ip_interface(source_ipv6_str).ip)

            # PTF uses Scapy to create packets, so this is ok to create
            # packets through PTF even though we are using Scapy to send the packets
            garp_pkt = testutils.simple_arp_packet(eth_src=source_mac,
                                                hw_snd=source_mac,
                                                ip_snd=source_ip,
                                                ip_tgt=source_ip, # Re-use server IP as target IP, since it is within the subnet of the VLAN IP
                                                arp_op=2)

            na_pkt = Ether(src=source_mac, dst=dut_mac) \
                   / IPv6(dst=dst_ipv6, src=source_ipv6) \
                   / ICMPv6ND_NA(tgt=source_ipv6, S=1, R=0, O=0) \
                   / ICMPv6NDOptSrcLLAddr(type=2, lladdr=source_mac)

            self.packets[intf_name] = [garp_pkt, na_pkt]

    def send_garp_packets(self):
        '''
        For each created GARP packet/interface pair, create an L2 socket.
        Then send every packet through its associated socket according to the self.interval
        '''
        self.gen_garp_packets()

        sockets = {}

        for intf, packet in list(self.packets.items()):
            socket = conf.L2socket(iface=intf)
            sockets[socket] = packet

        try:
            while True:
                for socket, packet_list in list(sockets.items()):
                    for packet in packet_list:
                        socket.send(packet)

                if self.interval is None:
                    break

                time.sleep(self.interval)

        finally:
            for socket in list(sockets.keys()):
                socket.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GARP Service')
    parser.add_argument('--conf', '-c', dest='conf_file', required=False, default='/tmp/garp_conf.json', action='store', help='The configuration file for GARP Service (default "/tmp/garp_conf.json")')
    parser.add_argument('--interval', '-i', dest='interval', required=False, type=int, default=None, action='store', help='The interval at which to re-send GARP messages. If None or not specified, messages will only be set once at service startup')
    args = parser.parse_args()
    conf_file = args.conf_file
    interval = args.interval

    garp_service = GarpService(conf_file, interval)
    garp_service.send_garp_packets()

import json, logging, struct, ipaddress
from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from scapy.all import sendp
from scapy.layers.inet import IP
from scapy.layers.l2 import Ether
from POKEMON_utils.headers import (
    ProbeHeader,
    SegmentHeader,
    TYPE_SOURCEROUTING,
    IP_PROTO_PROBE,
    TYPE_SOURCEROUTING_LINK,
    TYPE_SOURCEROUTING_SEG,
)
import threading
import time
import nnpy

records_lock = threading.Lock()

class RoutingController(object):

    def __init__(self, switch_name: str, queue_from_meta, queue_to_meta):
        logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
        self.topo = load_topo("topology.json")
        self.switch_name: str = switch_name
        self.connect_to_switch()
        self.install()
        self.queue_from_meta = queue_from_meta
        self.queue_to_meta = queue_to_meta
        self.records = {}

        # This thread periodically send probes to the dataplane
        self.probing_thread = threading.Thread(target=self.probing_loop)
        self.probing_period = 10  # number of seconds between 2 probes
        self.probing_thread.start()

        self.sniffing_digest_thread = threading.Thread(target=self.sniffing_digest_loop)
        self.sniffing_digest_thread.start()
        self.thrift_port = self.topo.get_thrift_port(self.switch_name)
        self.controller = SimpleSwitchThriftAPI(self.thrift_port)

    def install(self):
        self.controller.reset_state()
        self.set_table_defaults()
        self.route()
        self.sourcerouting()
        self.probe_setup()

    def connect_to_switch(self):
        thrift_port = self.topo.get_thrift_port(self.switch_name)
        self.controller = SimpleSwitchThriftAPI(thrift_port)
        self.controller_cpu_port = self.topo.get_ctl_cpu_intf(
            self.switch_name
        )  # port to send packets to the dataplane

    def set_table_defaults(self):
        self.controller.table_set_default("ipv4_lpm", "drop", [])
        self.controller.table_set_default("ecmp_group_to_nhop", "drop", [])
        self.controller.table_set_default("sourcerouting_link", "drop", [])
        self.controller.table_set_default(
            "sourcerouting_penultimate_hop", "NoAction", []
        )
        self.controller.table_set_default("count_outgoing_probes", "NoAction", [])
        self.controller.table_set_default("count_incoming_probes", "NoAction", [])

    def route(self):
        switch_ecmp_groups = {self.switch_name: {}}

        # sw_name = nom du switch d'intérêt
        # controller = nom du controlleur associé à ce switch
        for sw_dst in self.topo.get_p4switches():
            print("NAME:",sw_dst)

            # if its ourselves we create direct connections
            if self.switch_name == sw_dst:
                for host in self.topo.get_hosts_connected_to(self.switch_name):
                    sw_port = self.topo.node_to_node_port_num(self.switch_name, host)
                    host_ip = self.topo.get_host_ip(host) + "/32"
                    host_mac = self.topo.get_host_mac(host)

                    # add rule
                    logging.debug("table_add at {}:".format(self.switch_name))
                    self.controller.table_add(
                        "ipv4_lpm",
                        "set_nhop",
                        [str(host_ip)],
                        [str(host_mac), str(sw_port)],
                    )

            # add route for hosts directly connected to the destination.
            # And to the destination loopback for sourcerouting.
            else:
                paths = self.topo.get_shortest_paths_between_nodes(
                    self.switch_name, sw_dst
                )
                if len(paths) == 1:
                    next_hop = paths[0][1]

                    loopback_ip = f"100.0.0.{sw_dst[1:]}/32"
                    sw_port = self.topo.node_to_node_port_num(
                        self.switch_name, next_hop
                    )
                    dst_sw_mac = self.topo.node_to_node_mac(next_hop, self.switch_name)

                    # add rule
                    logging.debug("table_add at {}:".format(self.switch_name))
                    self.controller.table_add(
                        "ipv4_lpm",
                        "set_nhop",
                        [str(loopback_ip)],
                        [str(dst_sw_mac), str(sw_port)],
                    )
                elif len(paths) > 1:
                    next_hops = [x[1] for x in paths]
                    dst_macs_ports = [
                        (
                            self.topo.node_to_node_mac(next_hop, self.switch_name),
                            self.topo.node_to_node_port_num(self.switch_name, next_hop),
                        )
                        for next_hop in next_hops
                    ]
                    loopback_ip = f"100.0.0.{sw_dst[1:]}/32"

                    # check if the ecmp group already exists. The ecmp group is defined by the number of next
                    # ports used, thus we can use dst_macs_ports as key
                    if switch_ecmp_groups[self.switch_name].get(
                        tuple(dst_macs_ports), None
                    ):
                        ecmp_group_id = switch_ecmp_groups[self.switch_name].get(
                            tuple(dst_macs_ports), None
                        )
                        logging.debug("table_add at {}:".format(self.switch_name))
                        self.controller.table_add(
                            "ipv4_lpm",
                            "ecmp_group",
                            [str(loopback_ip)],
                            [str(ecmp_group_id), str(len(dst_macs_ports))],
                        )

                    # new ecmp group for this switch
                    else:
                        new_ecmp_group_id = (
                            len(switch_ecmp_groups[self.switch_name]) + 1
                        )
                        switch_ecmp_groups[self.switch_name][
                            tuple(dst_macs_ports)
                        ] = new_ecmp_group_id

                        # add group
                        for i, (mac, port) in enumerate(dst_macs_ports):
                            logging.debug("table_add at {}:".format(self.switch_name))
                            self.controller.table_add(
                                "ecmp_group_to_nhop",
                                "set_nhop",
                                [str(new_ecmp_group_id), str(i)],
                                [str(mac), str(port)],
                            )

                        # add forwarding rule
                        logging.debug("table_add at {}:".format(self.switch_name))
                        self.controller.table_add(
                            "ipv4_lpm",
                            "ecmp_group",
                            [str(loopback_ip)],
                            [
                                str(new_ecmp_group_id),
                                str(len(dst_macs_ports)),
                            ],
                        )

                for host in self.topo.get_hosts_connected_to(sw_dst):

                    if len(paths) == 1:
                        next_hop = paths[0][1]

                        host_ip = self.topo.get_host_ip(host) + "/24"
                        sw_port = self.topo.node_to_node_port_num(
                            self.switch_name, next_hop
                        )
                        dst_sw_mac = self.topo.node_to_node_mac(
                            next_hop, self.switch_name
                        )

                        # add rule
                        logging.debug("table_add at {}:".format(self.switch_name))
                        self.controller.table_add(
                            "ipv4_lpm",
                            "set_nhop",
                            [str(host_ip)],
                            [str(dst_sw_mac), str(sw_port)],
                        )

                    elif len(paths) > 1:
                        next_hops = [x[1] for x in paths]
                        dst_macs_ports = [
                            (
                                self.topo.node_to_node_mac(next_hop, self.switch_name),
                                self.topo.node_to_node_port_num(
                                    self.switch_name, next_hop
                                ),
                            )
                            for next_hop in next_hops
                        ]
                        host_ip = self.topo.get_host_ip(host) + "/24"

                        # check if the ecmp group already exists. The ecmp group is defined by the number of next
                        # ports used, thus we can use dst_macs_ports as key
                        if switch_ecmp_groups[self.switch_name].get(
                            tuple(dst_macs_ports), None
                        ):
                            ecmp_group_id = switch_ecmp_groups[self.switch_name].get(
                                tuple(dst_macs_ports), None
                            )
                            logging.debug("table_add at {}:".format(self.switch_name))
                            self.controller.table_add(
                                "ipv4_lpm",
                                "ecmp_group",
                                [str(host_ip)],
                                [str(ecmp_group_id), str(len(dst_macs_ports))],
                            )

                        # new ecmp group for this switch
                        else:
                            new_ecmp_group_id = (
                                len(switch_ecmp_groups[self.switch_name]) + 1
                            )
                            switch_ecmp_groups[self.switch_name][
                                tuple(dst_macs_ports)
                            ] = new_ecmp_group_id

                            # add group
                            for i, (mac, port) in enumerate(dst_macs_ports):
                                logging.debug(
                                    "table_add at {}:".format(self.switch_name)
                                )
                                self.controller.table_add(
                                    "ecmp_group_to_nhop",
                                    "set_nhop",
                                    [str(new_ecmp_group_id), str(i)],
                                    [str(mac), str(port)],
                                )

                            # add forwarding rule
                            logging.debug("table_add at {}:".format(self.switch_name))
                            self.controller.table_add(
                                "ipv4_lpm",
                                "ecmp_group",
                                [str(host_ip)],
                                [
                                    str(new_ecmp_group_id),
                                    str(len(dst_macs_ports)),
                                ],
                            )

    def sourcerouting(self):
        # Add an entry in both tables for each directly connected
        for neighbor in self.topo.get_neighbors(self.switch_name):
            if not self.topo.isSwitch(neighbor):
                continue

            neighbor_ip = f"100.0.0.{neighbor[1:]}/32"
            neighbor_mac = self.topo.node_to_node_mac(neighbor, self.switch_name)
            neighbor_port = self.topo.node_to_node_port_num(self.switch_name, neighbor)

            logging.debug("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "sourcerouting_link",
                "set_nhop",
                [str(neighbor_ip)],
                [str(neighbor_mac), str(neighbor_port)],
            )

            logging.debug("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "sourcerouting_penultimate_hop", "pop_segment", [str(neighbor_ip)], []
            )

    def probe_setup(self):
        # Associate target id and counter index
        self.counters_indexes = {}

        # Provide his probe_id to DataPlan
        self.controller.register_write(
            "probe_id", 0, 0x64000000 + int(self.switch_name[1:])
        )

        # Add add an entry for each router in topo in both table
        index = 0
        for sw in self.topo.get_p4switches():
            if sw == self.switch_name:
                continue

            sw_id = f"100.0.0.{sw[1:]}"
            self.counters_indexes[sw_id] = index
            index += 1

            logging.debug("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "count_outgoing_probes", "NoAction", [str(sw_id)], []
            )

            logging.debug("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "count_incoming_probes", "NoAction", [str(sw_id)], []
            )

    def probes_counters(self):
        """return updated probes counters as dictionary (key: target id, value : tuple(outgoing_probes, incoming_probes))"""

        probes_counters = {}
        for sw, index in self.counters_indexes.items():
            probes_counters[sw] = (
                self.controller.counter_read("outgoing_probes", index)[1],
                self.controller.counter_read("incoming_probes", index)[1],
            )
        return probes_counters

    def send_probe(self, origin, target, type=TYPE_SOURCEROUTING_SEG, recording=False):
        """Send one probe to cpu port"""

        ether = Ether(type=TYPE_SOURCEROUTING)
        segment1 = SegmentHeader(target=target, type=type, bottom=0)
        segment2 = SegmentHeader(target=origin, type=type, bottom=1)
        ip = IP(src=origin, dst=origin, proto=IP_PROTO_PROBE)
        probe = ProbeHeader(
            origin=origin,
            target=target,
            fresh=1,
            hit=0,
            recording=int(recording),
        )
        packet = ether / segment1 / segment2 / ip / probe
        logging.debug(str(packet))
        sendp(packet, iface=self.controller_cpu_port)

    def probing_direct_link(self):
        "Send a probe to all neighbor routers"

        my_loopback = "100.0.0." + self.switch_name[1:]
        for neighbor in self.topo.get_switches_connected_to(self.switch_name):
            neighbor_loopback = "100.0.0." + neighbor[1:]
            self.send_probe(my_loopback, neighbor_loopback, type=TYPE_SOURCEROUTING_LINK, recording=False)
    
    def probing_paths(self):
        "Send a hops recording probe to all routers"

        my_loopback = "100.0.0." + self.switch_name[1:]
        for target in self.topo.get_p4switches():
            if(target == self.switch_name):
                continue
            print(self.switch_name, target)
            target_loopback = "100.0.0." + target[1:]
            self.send_probe(my_loopback, target_loopback, type=TYPE_SOURCEROUTING_SEG, recording=True)
    
    def share_lossy_stats(self):
        self.queue_to_meta.put(json.dumps(self.probes_counters()))

    def share_record_paths(self):
        with records_lock:
            self.queue_to_meta.put(json.dumps(self.records))

    def probing_loop(self):
        while True:
            self.probing_direct_link()
            #self.probing_paths()
            time.sleep(self.probing_period)

    def sniffing_digest_loop(self):
        sub = nnpy.Socket(nnpy.AF_SP, nnpy.SUB)
        notifications_socket = (
            self.controller.client.bm_mgmt_get_info().notifications_socket
        )

        sub.connect(notifications_socket)
        sub.setsockopt(nnpy.SUB, nnpy.SUB_SUBSCRIBE, "")

        while True:
            msg = sub.recv()
            topic, device_id, ctx_id, list_id, buffer_id, num = struct.unpack("<iQiiQi", msg[:32])

            self.controller.client.bm_learning_ack_buffer(ctx_id, list_id, buffer_id)

            digest_payload= struct.unpack(">16iii", msg[32:104])
            origin = str(ipaddress.IPv4Address(digest_payload[16]))
            target = str(ipaddress.IPv4Address(digest_payload[17]))
            record = [str(ipaddress.IPv4Address(r)) for r in digest_payload[:16][::-1] if r != 0];
            print(origin, target, record)
            with records_lock:
                self.records[target] = record

            self.controller.client.bm_learning_ack_buffer(ctx_id, list_id, buffer_id)


    def main_loop(self):
        while True:
            received_order = self.queue_from_meta.get().split(";")
            if received_order[0] == "LOSSY_RATE":
                self.share_lossy_stats()
            elif received_order[0] == "SHORTEST_PATH":
                source = received_order[1]
                dest = received_order[2]
                self.share_record_paths()
            else:
                print(
                    "Error: received unexpected order from meta-controller : ",
                    received_order,
                )

from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
import sys


class RoutingController(object):

    def __init__(self, switch_name):

        self.topo = load_topo("topology.json")
        self.switch_name: str = switch_name
        self.counters_indexes = {}
        self.outgoing_probes = {}
        self.incoming_probes = {}
        self.init()

    def init(self):
        self.connect_to_switch()
        self.reset_state()
        self.set_table_defaults()

    def reset_state(self):
        self.controller.reset_state()

    def connect_to_switch(self):
        thrift_port = self.topo.get_thrift_port(self.switch_name)
        self.controller = SimpleSwitchThriftAPI(thrift_port)

    def set_table_defaults(self):
        self.controller.table_set_default("ipv4_lpm", "drop", [])
        self.controller.table_set_default("ecmp_group_to_nhop", "drop", [])
        self.controller.table_set_default("sourcerouting_link", "drop", [])
        self.controller.table_set_default("sourcerouting_penultimate_hop", "NoAction", [])
        self.controller.table_set_default("count_outgoing_probes", "NoAction", [])
        self.controller.table_set_default("count_incoming_probes", "NoAction", [])

    def route(self):

        switch_ecmp_groups = {
            self.switch_name: {} 
        }

        # sw_name = nom du switch d'intérêt
        # controller = nom du controlleur associé à ce switch
        for sw_dst in self.topo.get_p4switches():

            # if its ourselves we create direct connections
            if self.switch_name == sw_dst:
                for host in self.topo.get_hosts_connected_to(self.switch_name):
                    sw_port = self.topo.node_to_node_port_num(self.switch_name, host)
                    host_ip = self.topo.get_host_ip(host) + "/32"
                    host_mac = self.topo.get_host_mac(host)

                    # add rule
                    print("table_add at {}:".format(self.switch_name))
                    self.controller.table_add(
                        "ipv4_lpm",
                        "set_nhop",
                        [str(host_ip)],
                        [str(host_mac), str(sw_port)],
                    )

            # add route for hosts directly connected to the destination.
            # And to the destination loopback for sourcerouting.
            else:
                paths = self.topo.get_shortest_paths_between_nodes(self.switch_name, sw_dst)
                if len(paths) == 1:
                    next_hop = paths[0][1]

                    loopback_ip = f"100.0.0.{sw_dst[1:]}/32"
                    sw_port = self.topo.node_to_node_port_num(self.switch_name, next_hop)
                    dst_sw_mac = self.topo.node_to_node_mac(next_hop, self.switch_name)

                    # add rule
                    print("table_add at {}:".format(self.switch_name))
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
                        print("table_add at {}:".format(self.switch_name))
                        self.controller.table_add(
                            "ipv4_lpm",
                            "ecmp_group",
                            [str(loopback_ip)],
                            [str(ecmp_group_id), str(len(dst_macs_ports))],
                        )

                    # new ecmp group for this switch
                    else:
                        new_ecmp_group_id = len(switch_ecmp_groups[self.switch_name]) + 1
                        switch_ecmp_groups[self.switch_name][
                            tuple(dst_macs_ports)
                        ] = new_ecmp_group_id

                        # add group
                        for i, (mac, port) in enumerate(dst_macs_ports):
                            print("table_add at {}:".format(self.switch_name))
                            self.controller.table_add(
                                "ecmp_group_to_nhop",
                                "set_nhop",
                                [str(new_ecmp_group_id), str(i)],
                                [str(mac), str(port)],
                            )

                        # add forwarding rule
                        print("table_add at {}:".format(self.switch_name))
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
                        sw_port = self.topo.node_to_node_port_num(self.switch_name, next_hop)
                        dst_sw_mac = self.topo.node_to_node_mac(next_hop, self.switch_name)

                        # add rule
                        print("table_add at {}:".format(self.switch_name))
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
                                self.topo.node_to_node_port_num(self.switch_name, next_hop),
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
                            print("table_add at {}:".format(self.switch_name))
                            self.controller.table_add(
                                "ipv4_lpm",
                                "ecmp_group",
                                [str(host_ip)],
                                [str(ecmp_group_id), str(len(dst_macs_ports))],
                            )

                        # new ecmp group for this switch
                        else:
                            new_ecmp_group_id = len(switch_ecmp_groups[self.switch_name]) + 1
                            switch_ecmp_groups[self.switch_name][
                                tuple(dst_macs_ports)
                            ] = new_ecmp_group_id

                            # add group
                            for i, (mac, port) in enumerate(dst_macs_ports):
                                print("table_add at {}:".format(self.switch_name))
                                self.controller.table_add(
                                    "ecmp_group_to_nhop",
                                    "set_nhop",
                                    [str(new_ecmp_group_id), str(i)],
                                    [str(mac), str(port)],
                                )

                            # add forwarding rule
                            print("table_add at {}:".format(self.switch_name))
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
            if(not self.topo.isSwitch(neighbor)):
                continue
            
            neighbor_ip = f"100.0.0.{neighbor[1:]}/32"
            neighbor_mac = self.topo.node_to_node_mac(self.switch_name, neighbor)
            neighbor_port = self.topo.node_to_node_port_num(neighbor, self.switch_name) 

            print("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "sourcerouting_link",
                "set_nhop",
                [str(neighbor_ip)],
                [str(neighbor_mac), str(neighbor_port)]
            )

            print("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "sourcerouting_penultimate_hop",
                "pop_segment",
                [str(neighbor_ip)],
                []
            )

    def probe_setup(self):
        # Add add an entry for each router in topo in both table
        index = 0
        for sw in self.topo.get_p4switches():
            if(sw == self.switch_name):
                continue

            sw_id = f"100.0.0.{sw[1:]}"
            self.counters_indexes[sw_id] = index;
            index+=1

            print("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "count_outgoing_probes",
                "NoAction",
                [str(sw_id)],
                []
            )

            print("table_add at {}:".format(self.switch_name))
            self.controller.table_add(
                "count_incoming_probes",
                "NoAction",
                [str(sw_id)],
                []
            )

    def fetch_probe_counters(self):
        for sw, index in self.counters_indexes.items():
            self.outgoing_probes[sw] = self.controller.counter_read("outgoing_probes", index)[1]
            self.outgoing_probes[sw] = self.controller.counter_read("incoming_probes", index)[1]


    def main_loop(self):
        self.route()
        self.sourcerouting()
        self.probe_setup()


if __name__ == "__main__":
    switch = sys.argv[1]
    controller = RoutingController(switch).main_loop()

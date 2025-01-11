from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from routing_controller import RoutingController
import sys


class StupidController(RoutingController):

    def __init__(self, switch_name, queue_from_meta, queue_to_meta):
        super().__init__(switch_name, queue_from_meta, queue_to_meta)

    def init(self):
        self.connect_to_switch()
        self.reset_state()
        self.set_table_defaults()
        self.push_number_of_ports()

    def push_number_of_ports(self):
        number_of_ports: int = len(self.topo.get_interfaces_to_node(self.switch_name))
        self.controller.register_write("number_of_ports", 0, number_of_ports)
        print("\nAdded ", number_of_ports, "to the register number_of_ports\n")


if __name__ == "__main__":
    switch = sys.argv[1]
    controller = StupidController(switch).main()

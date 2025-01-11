from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from routing_controller import RoutingController
from stupid_controller import StupidController
import threading
import queue
import sys
import json
import cmd


class MetaController(cmd.Cmd):

    def __init__(self, queues_from_meta, queues_to_meta):
        super().__init__()
        self.prompt = ">>>"
        self.topo = load_topo("topology.json")
        self.controllers = {}
        self.queues_from_meta = queues_from_meta
        self.queues_to_meta = queues_to_meta

        self.lossy_rates = {}

        self.ask_lossy_rate_message = "LOSSY_RATE"
        self.ask_shortest_path_stats = "SHORTEST_PATH"

        self.init()

    def init(self):
        self.connect_to_switches()
        self.reset_states()

    def read_register_on(self, switch_id, register_name: str, index: int) -> int | list:
        return switch_id.register_read(register_name, index)

    def write_register_on(
        self, switch_id, register_name: str, index: int, value: int
    ) -> None:
        switch_id.register_write(register_name, index, value)
        return None

    # def install_entry_on(self, switch_id, table_name : str, entry : str):
    #     switch_id.table_add(table_name, )

    # def remove_entry_on(self, switch_id, table_name : str, entry : int):
    #     switch_id.table_delete(table_name, entry_handle, quiet=False)

    def reset_states(self):
        [controller.reset_state() for controller in self.controllers.values()]

    def connect_to_switches(self):
        for p4switch in self.topo.get_p4switches():
            thrift_port = self.topo.get_thrift_port(p4switch)
            self.controllers[p4switch] = SimpleSwitchThriftAPI(thrift_port)

    def do_ask_lossy_rates(self, args):
        """Ask all controllers to publish their stats about losses"""
        self.ask_sonde(self.ask_lossy_rate_message)

    def do_ask_shortest_paths_stats(self, args):
        """Ask all controllers to publish their stats about shortest path stats"""
        self.ask_sonde(self.ask_shortest_path_stats)

    def display_lossy_rates(self, sw_name):
        for sw_name, controller in self.controllers.items():
            dico = json.loads(self.lossy_rates[sw_name])
            print(f"Rates of {sw_name} : ")
            for sw_dst, tuples in dico.items():
                ratio = tuples[1] / tuples[0] if tuples[0] != 0 else 0
                print(f"{'dest':<15}{'outgoing':<15}{'ingoing':<15}{'ratio':<15}")
                print(f"{sw_dst:<15}{tuples[0]:<15}{tuples[1]:<15}{ratio:<15}")
            print("")

    def ask_sonde(self, sonde_kind):
        for sw_name, controller in self.controllers.items():
            print("Sending a request to", sw_name)
            self.queues_from_meta[sw_name].put(sonde_kind)

        for sw_name, controller in self.controllers.items():
            if sonde_kind == self.ask_lossy_rate_message:
                print("Trying to receive the response from", sw_name)
                self.lossy_rates[sw_name] = self.queues_to_meta[sw_name].get()
            elif sonde_kind == self.ask_shortest_path_stats:
                print("Not implemented yet")
        self.display_lossy_rates(sw_name)

    def do_exit(self, arg):
        """Exit the shell"""

        print("Goodbye!")
        return True
    
    def emptyline(self):
        # Overriding emptyline to do nothing when Enter is pressed
        pass


def get_switches_from_topo(config_path: str):
    with open(config_path, "r") as j:
        data = json.load(j)

    switches = data["topology"]["switches"]
    print("JSON topology succesfully read !")
    return switches


def main(config_path: str):
    switches = get_switches_from_topo(config_path)
    print("-------------------------------------------\n", switches)

    threads = []

    queues_from_meta = {}
    queues_to_meta = {}

    for switch, details in switches.items():
        print("\n---------------------------------------------------------------------")
        print("Starting a thread for", switch)
        p4_file = details.get("p4_src")
        queues_from_meta[switch] = queue.Queue()
        queues_to_meta[switch] = queue.Queue()
        if p4_file == "p4src/simple_router.p4":
            thread = threading.Thread(
                target=lambda: RoutingController(
                    switch, queues_from_meta[switch], queues_to_meta[switch]
                ).main_loop()
            )
            print("Starting normal controller")
        elif p4_file == "p4src/simple_router_stupid.p4":
            thread = threading.Thread(
                target=lambda: StupidController(
                    switch, queues_from_meta[switch], queues_to_meta[switch]
                ).main_loop()
            )
            print("Starting stupid controller")
        elif p4_file == "p4src/simple_router_loss.p4":
            thread = threading.Thread(
                target=lambda: RoutingController(
                    switch, queues_from_meta[switch], queues_to_meta[switch]
                ).main_loop()
            )
            print("Starting lossy controller")
        else:
            print(
                "The p4src file specified doesnt match any of the handled cases : ",
                p4_file,
            )
            sys.exit(1)
        threads.append(thread)
        thread.start()

    meta_controller_thread = threading.Thread(
        target=lambda: MetaController(queues_from_meta, queues_to_meta).cmdloop(
            "Welcome to the meta controller shell. Type 'help' for commands."
        )
    )
    threads.append(meta_controller_thread)
    meta_controller_thread.start()

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python3",
            sys.argv[0],
            "topo.json",
        )
        sys.exit(1)
    main(sys.argv[1])

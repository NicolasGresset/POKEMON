from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI
from routing_controller import RoutingController
from stupid_controller import StupidController
import threading
import queue
import sys
import json
import cmd
import time, io


class MetaController(cmd.Cmd):

    def __init__(self, queues_from_meta, queues_to_meta):
        super().__init__()
        self.prompt = ">>>"
        self.topo = load_topo("topology.json")
        self.switches = self.topo.get_p4switches()
        self.queues_from_meta = queues_from_meta
        self.queues_to_meta = queues_to_meta

        self.lossy_rates = {}

        self.ask_lossy_rate_message = "LOSSY_RATE"
        self.ask_shortest_path_stats = "SHORTEST_PATH"

        self.retrieve_stats_thread = threading.Thread(target=self.retrieve_stats_loop)
        self.retrieve_stats_period = (
            10  # number of seconds between each value retrieving process
        )

        self.retrieve_stats_thread.start()

    def read_register_on(self, switch_id, register_name: str, index: int) -> int | list:
        return switch_id.register_read(register_name, index, show=False)

    def write_register_on(
        self, switch_id, register_name: str, index: int, value: int
    ) -> None:
        switch_id.register_write(register_name, index, value)
        return None

    # def install_entry_on(self, switch_id, table_name : str, entry : str):
    #     switch_id.table_add(table_name, )

    # def remove_entry_on(self, switch_id, table_name : str, entry : int):
    #     switch_id.table_delete(table_name, entry_handle, quiet=False)

    def do_ask_lossy_rates(self, args):
        """Ask all controllers to publish their stats about losses"""
        self.display_lossy_rates()

    def do_ask_shortest_paths_stats(self, args):
        """Ask all controllers to publish their stats about shortest path stats"""
        # display stats about shortest paths
        pass

    def display_lossy_rates(self):
        for sw_name in self.switches:
            dico = json.loads(self.lossy_rates[sw_name])
            print(f"Rates of {sw_name} : ")
            for sw_dst, tuples in dico.items():
                ratio = tuples[1] / tuples[0] if tuples[0] != 0 else 0
                print(f"{'dest':<15}{'outgoing':<15}{'incoming':<15}{'ratio':<15}")
                print(f"{sw_dst:<15}{tuples[0]:<15}{tuples[1]:<15}{ratio:<15}")
            print("")

    def retrieve_stats(self, sonde_kind):
        for sw_name in self.switches:
            self.queues_from_meta[sw_name].put(sonde_kind)
        
        for sw_name in self.switches:
            if sonde_kind == self.ask_lossy_rate_message:
                self.lossy_rates[sw_name] = self.queues_to_meta[sw_name].get()
            elif sonde_kind == self.ask_shortest_path_stats:
                print("Received shortest paths stats : Not implemented yet")

    def retrieve_stats_loop(self):
        """Ask all controllers to share stats each retrieve_stat_period seconds"""
        while True:
            self.retrieve_stats(self.ask_lossy_rate_message)
            self.retrieve_stats(self.ask_shortest_path_stats)
            time.sleep(self.retrieve_stats_period)

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

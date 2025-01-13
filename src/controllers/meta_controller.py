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


class MetaController:

    def __init__(self, queues_from_meta, queues_to_meta):
        super().__init__()
        self.prompt = ">>>"
        self.topo = load_topo("topology.json")
        self.switches = self.topo.get_p4switches()
        self.queues_from_meta = queues_from_meta
        self.queues_to_meta = queues_to_meta

        self.lossy_rates = {}
        self.shortest_paths = {}

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

    def display_shortest_paths(self):
        for sw_name in self.switches:
            dico = json.loads(self.shortest_paths[sw_name])
            self.print(f"Paths of {sw_name}")
            self.print(f"{'dest':<15}{'paths':<65}")
            for sw_dst, paths in dico.items():
                sw_dst_transformed = "s" + sw_dst.split(".")[-1]
                paths_transformed = list(map(lambda elem : "s"+ elem.split(".")[-1], paths))
                paths_string = ",".join(paths_transformed)
                self.print(f"{sw_dst_transformed:<15}{paths_string:<65}")
            self.print("")

    def display_lossy_rates(self):
        for sw_name in self.switches:
            dico = json.loads(self.lossy_rates[sw_name])
            self.print("-"*60)
            self.print(f"Rates of {sw_name} : ")
            self.print(f"{'dest':<15}{'outgoing':<15}{'incoming':<15}{'ratio':<15}")
            for sw_dst, tuples in dico.items():
                sw_dst_transformed = "s" + sw_dst.split(".")[-1]
                ratio = tuples[1] / tuples[0] if tuples[0] != 0 else 0
                if ratio != 1 and tuples[0] != 0:
                    self.print("\033[31m", end='')
            
                self.print(f"{sw_dst_transformed:<15}{tuples[0]:<15}{tuples[1]:<15}{ratio:<15}")

                if ratio != 1 and tuples[0] != 0:
                    self.print("\033[0m", end='')
            self.print("")

    def retrieve_stats(self, sonde_kind):
        for sw_name in self.switches:
            self.queues_from_meta[sw_name].put(sonde_kind)

        for sw_name in self.switches:
            if sonde_kind == self.ask_lossy_rate_message:
                self.lossy_rates[sw_name] = self.queues_to_meta[sw_name].get()
            elif sonde_kind == self.ask_shortest_path_stats:
                self.shortest_paths[sw_name] = self.queues_to_meta[sw_name].get()

    def retrieve_stats_loop(self):
        """Ask all controllers to share stats each retrieve_stat_period seconds"""
        while True:
            self.retrieve_stats(self.ask_lossy_rate_message)
            self.retrieve_stats(self.ask_shortest_path_stats)
            time.sleep(self.retrieve_stats_period)

    def print(self, *args, **kwargs):
        """Utiliser sys.__stdout__ pour les affichages explicites"""
        print(*args, file=sys.__stdout__, **kwargs)
    
    def listen_user_input_loop(self):
        while True:
            self.print(">>>")
            user_input=input()
            if user_input == "":
                continue
            elif user_input == "h" or user_input == "help":
                self.print("Available commands : \nhelp (h)\nask_lossy_rates (l)\nask_shortest_paths_stats (s)")
            elif user_input == "ask_lossy_rates" or user_input == "l":
                self.display_lossy_rates()
            elif user_input == "ask_shortest_paths_stats" or user_input == "s":
                self.display_shortest_paths()
            else:
                self.print("Unrecognized command, type help for available commands")

            



def get_switches_from_topo(config_path: str):
    with open(config_path, "r") as j:
        data = json.load(j)

    switches = data["topology"]["switches"]
    print("JSON topology succesfully read !")
    return switches


def main(config_path: str):
    switches = get_switches_from_topo(config_path)

    threads = []

    queues_from_meta = {}
    queues_to_meta = {}

    for switch, details in switches.items():
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
        target=lambda: MetaController(
            queues_from_meta, queues_to_meta
        ).listen_user_input_loop()
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

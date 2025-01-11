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

    def do_send_sonde(self, args):
        """Send a sonde with the given identifier"""
        try:
            arg_list = args.split()
            if len(arg_list) != 2:
                print("Error: send_sonde requires exactly 2 arguments.")
                return

            identifier, message = arg_list

        except Exception as e:
            print(f"An error occurred: {e}")
        self.send_sonde(identifier, message)

    def send_sonde(self, identifier, message):
        self.queues_from_meta[identifier].put(message)
        received_msg = self.queues_to_meta[identifier].get()
        print("(meta-controller) received response : ", received_msg)

    def do_exit(self, arg):
        """Exit the shell"""

        print("Goodbye!")
        return True


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
        if p4_file == "p4src/routing_router.p4":
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

    meta_controller_thread = threading.Thread(
        target=lambda: MetaController(queues_from_meta, queues_to_meta).cmdloop(
            "Welcome to the meta controller shell. Type 'help' for commands."
        )
    )
    threads.append(meta_controller_thread)

    for thread in threads:
        thread.start()

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

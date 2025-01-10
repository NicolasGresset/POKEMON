from p4utils.utils.helper import load_topo
from p4utils.utils.sswitch_thrift_API import SimpleSwitchThriftAPI

class MetaController(object):

    def __init__(self):

        self.topo = load_topo('topology.json')
        self.controllers = {}
        self.init()

    def init(self):
        self.connect_to_switches()
        self.reset_states()

    def read_register_on(self, switch_id, register_name : str, index : int) -> int | list:
        return switch_id.register_read(register_name, index)

    def write_register_on(self, switch_id, register_name : str, index : int, value : int) -> None:
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

    def main(self):
        pass

if __name__ == "__main__":
    controller = MetaController().main()

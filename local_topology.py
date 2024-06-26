import typing as tp
import argparse
import networkx as nx
from pathlib import Path
import sys
import io
import matplotlib.pyplot as plt
import matplotlib.image as mpimg


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument('input_dot_filename', help="Input .dot file name")
    parser.add_argument('input_cmds_filename', help="Path to instructions")
    parser.add_argument('-i', action='store_true', help="Parse extra commands from stdin after input_cmds_filename contents")
    parser.add_argument('--twopi', type=int, help="If set, use twopi at this ranksep value")
    return parser

class OutputGraphBuilder:
    def __init__(self, inG: nx.DiGraph):
        self.inG = inG
        self.outG = nx.DiGraph()

    def _get_input_node_name_from_label(self, search_term: str) -> str:
        # TODO store in dict to avoid repeat lookups
        def is_hit(props: tp.Dict[str, str], search_term: str) -> bool:
            if 'label' not in props:
                return False
            tok = props['label'].strip('<').strip('>').split('<BR/>')
            return search_term == tok[0]

        candidates = [name for name,props in self.inG.nodes(data=True) if is_hit(props, search_term)]
        assert len(candidates) > 0, f"Did not find any node name for label:\n{search_term}"
        assert len(candidates) == 1, f"Did not find unique node name for label:\n{search_term} -> {candidates}"
        return candidates[0]

    def _add_out_node(self, node: str, is_label: bool=True) -> str:
        # TODO refactor so labels/names are done consistently from the lookup dict
        if is_label:
            node_name = self._get_input_node_name_from_label(node)
        else:
            node_name = node

        if node_name not in self.outG:
            assert node_name in inG, f"No such node in input .dot file:\n{node_name}"
            props = {'label': inG.nodes[node_name]['label']}
            if 'shape' in inG.nodes[node_name]:
                props['shape'] = inG.nodes[node_name]['shape']
            self.outG.add_node(node_name, **props)

        return node_name

    def add_link_between(self, from_node: str, to_node: str):
        from_name = self._add_out_node(from_node)
        to_name = self._add_out_node(to_node)
        self.outG.add_edge(from_name, to_name)

    def add_predecessors_of(self, target_node: str):
        self._add_out_node(target_node)

        # TODO refactor with add_successors_of()
        target_node_name = self._get_input_node_name_from_label(target_node)
        other_node_names = list(self.inG.predecessors(target_node_name))
        for other_node_name in other_node_names:
            self._add_out_node(other_node_name, is_label=False)
            # TODO note reverse direction here
            self.outG.add_edge(other_node_name, target_node_name)

    def add_successors_of(self, target_node: str):
        self._add_out_node(target_node)

        target_node_name = self._get_input_node_name_from_label(target_node)
        child_node_names = list(nx.neighbors(self.inG, target_node_name))
        for child_node_name in child_node_names:
            self._add_out_node(child_node_name, is_label=False)
            self.outG.add_edge(target_node_name, child_node_name)

    def add_chain_of_nodes(self, source_node_label: str, target_node_label: str):
        from_name = self._get_input_node_name_from_label(source_node_label)
        to_name = self._get_input_node_name_from_label(target_node_label)
        # TODO catch the nx.exception.NetworkXNoPath, report as labels not names
        chain_of_names = nx.shortest_path(self.inG, source=from_name, target=to_name)

        self._add_out_node(chain_of_names[0], is_label=False)
        for i in range(1, len(chain_of_names)):
            self._add_out_node(chain_of_names[i], is_label=False)
            self.outG.add_edge(chain_of_names[i-1], chain_of_names[i])

def parse_line(line: str, builder: OutputGraphBuilder, outF):
    save_line = True
    num_nodes_before = builder.outG.number_of_nodes()
    num_edges_before = builder.outG.number_of_edges()
    if "->" in line:
        tokens = line.split("->")
        assert len(tokens) > 1, f"Need >= 1 token around '->':\n{line}"
        tokens = [tok.strip() for tok in tokens]
        for i in range(1,len(tokens)):
            if tokens[i] == "*":
                assert tokens[i-1] != "*", f"Can't have double * around '->':\n{line}"
                builder.add_successors_of(tokens[i-1])
            elif tokens[i-1] == "*":
                builder.add_predecessors_of(tokens[i])
            else:
                builder.add_link_between(tokens[i-1], tokens[i])
    elif "==>" in line:
        tokens = line.split("==>")
        assert len(tokens) == 2, f"Only 1 token allowed before and after '==>':\n{line}"
        tokens = [tok.strip() for tok in tokens]

        builder.add_chain_of_nodes(tokens[0], tokens[1])
    else:
        save_line = False

    if save_line:
        num_nodes_after = builder.outG.number_of_nodes()
        num_edges_after = builder.outG.number_of_edges()

        if ( num_nodes_after != num_nodes_before \
          or num_edges_after != num_edges_before):

            outF.write(line+"\n")
        else:
            print(f"This line did nothing: {line}")

def view_pydot(pdot):
    png_str = pdot.create_png(prog='dot')
    sio = io.BytesIO()
    sio.write(png_str)
    sio.seek(0)
    img = mpimg.imread(sio)

    plt.imshow(img, aspect='equal')
    plt.show()

def get_graph_to_draw(inG: nx.DiGraph, args) -> nx.DiGraph:
    builder = OutputGraphBuilder(inG)
    history_file = Path("history.txt")
    if history_file.exists():
        history_file.unlink()

    with open(history_file, 'w') as outF:
        with open(args.input_cmds_filename, 'r') as inF:
            for line in inF:
                parse_line(line.strip(), builder, outF)

        if args.i:
            print("enter 'exit' to end")
            for line in sys.stdin:
                if line.strip() == "exit":
                    break
                parse_line(line.strip(), builder, outF)
                view_pydot(nx.nx_pydot.to_pydot(builder.outG))

    return builder.outG

if __name__ == '__main__':
    args = setup_parser().parse_args()
    inG = nx.DiGraph(nx.nx_pydot.read_dot(args.input_dot_filename))

    outG = get_graph_to_draw(inG, args)
    nx.nx_pydot.write_dot(outG, "out.dot")

    if args.twopi is None:
        nx.nx_pydot.to_pydot(outG).write_jpg("out.jpg")
    else:
        pydotG = nx.nx_pydot.to_pydot(outG)
        pydotG.set_ranksep(args.twopi)
        pydotG.write_jpg("out.jpg", prog="twopi")


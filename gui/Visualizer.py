import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

class Visualizer:
    COLORS = {"switch": "#1f77b4", "host_active": "#2ca02c", "host_blocked": "#e74c3c"}

    @staticmethod
    def build_graph(topo_data):
        G = nx.Graph()
        for s in topo_data["switches"]:
            G.add_node(s, kind="switch")
        for h in topo_data["hosts"]:
            G.add_node(h, kind="host")
        for link in topo_data["links"]:
            n1, n2 = link["node1"], link["node2"]
            G.add_edge(n1, n2, link_type=link.get("type", "?"))
        return G

    @classmethod
    def draw_topology(cls, G, blocked_hosts, path_edges=None, active_packets=None):
        fig, ax = plt.subplots(figsize=(12, 7))
        ax.set_facecolor("#0a0e1a")
        fig.patch.set_facecolor("#0a0e1a")
        pos = nx.spring_layout(G, seed=42)

        # Base edges
        nx.draw_networkx_edges(G, pos, edge_color="#ecf0f1", width=2, ax=ax)

        # Active packets
        if active_packets:
            active_edges = []
            for src, dst in active_packets:
                if G.has_node(src) and G.has_node(dst):
                    try:
                        p = nx.shortest_path(G, src, dst)
                        active_edges += list(zip(p, p[1:]))
                    except Exception:
                        pass
            if active_edges:
                nx.draw_networkx_edges(G, pos, edgelist=list(set(active_edges)),
                                       edge_color="#ff9800", width=5, alpha=0.7, ax=ax)

        # Path edges
        if path_edges:
            nx.draw_networkx_edges(G, pos, edgelist=path_edges,
                                   edge_color="#3498db", width=5, ax=ax)

        # Nodes
        node_colors = []
        node_sizes  = []
        for node in G.nodes:
            kind = G.nodes[node]["kind"]
            if kind == "switch":
                node_colors.append(cls.COLORS["switch"])
                node_sizes.append(2500)
            else:
                node_colors.append(cls.COLORS["host_blocked"] if node in blocked_hosts else cls.COLORS["host_active"])
                node_sizes.append(1200)

        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, ax=ax)
        nx.draw_networkx_labels(G, pos, font_color="white", font_weight="bold", font_size=10, ax=ax)

        # Legend
        legend_items = [
            mpatches.Patch(color=cls.COLORS["switch"], label="Switch"),
            mpatches.Patch(color=cls.COLORS["host_active"], label="Host attivo"),
            mpatches.Patch(color=cls.COLORS["host_blocked"], label="Host isolato"),
            mpatches.Patch(color="#3498db", label="Percorso Dijkstra"),
            mpatches.Patch(color="#ff9800", label="Traffico attivo"),
        ]
        ax.legend(handles=legend_items, loc="lower left",
                  facecolor="#0d1b2a", edgecolor="#334",
                  labelcolor="white", fontsize=9, framealpha=0.9)
        ax.set_axis_off()
        plt.tight_layout()
        return fig

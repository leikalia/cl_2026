from neo4j import GraphDatabase
from string import ascii_lowercase, digits
from random import choice
import json


class Neo4jRepository:
    def __init__(self, uri, username, password, namespace_title):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.namespace_title = namespace_title

    def close(self):
        self.driver.close()

    def get_all_nodes_and_arcs(self):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (n)
                OPTIONAL MATCH (n)-[r]->(m)
                RETURN n, r
            """)

            nodes_with_arcs = []
            for record in result:
                node = self.collect_node(record["n"])
                arcs = []
                if record["r"] is not None:
                    arcs.append(self.collect_arc(record["r"]))
                nodes_with_arcs.append((node, arcs))

            return nodes_with_arcs

    def get_nodes_by_labels(self, labels):
        label_str = self._format_labels(labels)
        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (n{label_str})
                RETURN n
            """)
            return [self.collect_node(r["n"]) for r in result]

    def get_node_by_uri(self, uri):
        with self.driver.session() as session:
            record = session.run("""
                MATCH (n {uri:$uri})
                RETURN n
            """, uri=uri).single()
            return self.collect_node(record["n"]) if record else None

    def create_node(self, params):
        labels = params.get("labels", [])
        properties = params.get("properties", {})

        if "description" not in properties:
            properties["description"] = ""

        if "uri" not in properties:
            properties["uri"] = self.generate_random_string()

        label_str = self._format_labels(labels)
        props_str = self._format_properties(properties)

        with self.driver.session() as session:
            record = session.run(f"""
                CREATE (n{label_str} {props_str})
                RETURN n
            """).single()
            return self.collect_node(record["n"]) if record else None

    def create_arc(self, node1_uri, node2_uri, params):
        labels = params.get("labels", [])
        properties = params.get("properties", {})

        label_str = self._format_labels(labels)
        props_str = self._format_properties(properties)

        with self.driver.session() as session:
            record = session.run(f"""
                MATCH (from {{uri:$u1}}), (to {{uri:$u2}})
                CREATE (from)-[r{label_str} {props_str}]->(to)
                RETURN r
            """, u1=node1_uri, u2=node2_uri).single()

            return self.collect_arc(record["r"]) if record else None

    def delete_node_by_uri(self, uri):
        with self.driver.session() as session:
            record = session.run("""
                MATCH (n {uri:$uri})
                DETACH DELETE n
                RETURN COUNT(n) as deleted
            """, uri=uri).single()
            return record["deleted"] if record else 0

    def delete_arc_by_id(self, arc_id):
        with self.driver.session() as session:
            record = session.run("""
                MATCH ()-[r]->()
                WHERE id(r) = $arc_id
                DELETE r
                RETURN COUNT(r) as deleted
            """, arc_id=arc_id).single()
            return record["deleted"] if record else 0

    def update_node(self, uri, params):
        if not params:
            return None

        set_clauses = []
        for k, v in params.items():
            if isinstance(v, str):
                set_clauses.append(f'n.`{k}` = "{v}"')
            else:
                set_clauses.append(f'n.`{k}` = {json.dumps(v)}')

        set_statement = ", ".join(set_clauses)

        with self.driver.session() as session:
            record = session.run(f"""
                MATCH (n {{uri:$uri}})
                SET {set_statement}
                RETURN "OK" as status
            """, uri=uri).single()
            return "OK" if record else None

    # IMPORTANT:
    # tail uses only safe chars: a-z 0-9 _
    # and ALWAYS starts with a letter
    def generate_random_string(self, length=32):
        first = choice(ascii_lowercase)
        alphabet = ascii_lowercase + digits + "_"
        rest = "".join(choice(alphabet) for _ in range(length - 1))
        tail = first + rest
        return f"http://{self.namespace_title}.com/{tail}"

    def collect_node(self, node):
        props = dict(node)
        return TNode(
            uri=props.get("uri"),
            description=props.get("description", ""),
            label=list(node.labels)
        )

    def collect_arc(self, arc):
        nodes = arc.nodes
        return TArc(
            id=arc.id,
            uri=arc.type,
            node_uri_from=dict(nodes[0]).get("uri"),
            node_uri_to=dict(nodes[1]).get("uri")
        )

    def _format_labels(self, labels):
        if not labels:
            return ""
        return ":" + ":".join(f"`{l}`" for l in labels)

    def _format_properties(self, properties):
        if not properties:
            return ""
        items = []
        for k, v in properties.items():
            if isinstance(v, str):
                items.append(f'`{k}`: "{v}"')
            else:
                items.append(f'`{k}`: {json.dumps(v)}')
        return "{" + ", ".join(items) + "}"


class TNode:
    def __init__(self, uri, description, label):
        self.uri = uri
        self.description = description
        self.label = label

    def __str__(self):
        return f"[uri={self.uri}, desc={self.description}, labels={self.label}]"


class TArc:
    def __init__(self, id, uri, node_uri_from, node_uri_to):
        self.id = id
        self.uri = uri
        self.node_uri_from = node_uri_from
        self.node_uri_to = node_uri_to

    def __str__(self):
        return f"[id={self.id}, uri={self.uri}, from={self.node_uri_from}, to={self.node_uri_to}]"
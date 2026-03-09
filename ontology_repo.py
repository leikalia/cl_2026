from main import Neo4jRepository


class OntologyRepository:
    def __init__(self, repo: Neo4jRepository):
        self.repo = repo

    def _tail_from_uri(self, uri: str) -> str:
        return uri.rsplit("/", 1)[-1]

    def _subtree_class_uris(self, class_uri: str):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})
                MATCH (d:Class)-[:SUBCLASS_OF*0..]->(c)
                RETURN DISTINCT d.uri as u
            """, u=class_uri)
            return [r["u"] for r in res if r["u"]]


    def get_ontology(self):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (n)
                WHERE n:Class OR n:Object OR n:DatatypeProperty OR n:ObjectProperty
                OPTIONAL MATCH (n)-[r]->(m)
                WHERE m:Class OR m:Object OR m:DatatypeProperty OR m:ObjectProperty
                RETURN n, r, m
            """)
            return [r.data() for r in res]

    def get_ontology_parent_classes(self):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class)
                WHERE NOT (c)-[:SUBCLASS_OF]->(:Class)
                RETURN c
            """)
            return [r["c"] for r in res]

    def get_class(self, class_uri: str):
        return self.repo.get_node_by_uri(class_uri)

    def get_class_parents(self, class_uri: str):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})-[:SUBCLASS_OF*1..]->(p:Class)
                RETURN DISTINCT p
            """, u=class_uri)
            return [r["p"] for r in res]

    def get_class_children(self, class_uri: str):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})<-[:SUBCLASS_OF*1..]-(ch:Class)
                RETURN DISTINCT ch
            """, u=class_uri)
            return [r["ch"] for r in res]

    def get_class_objects(self, class_uri: str):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})
                MATCH (sub:Class)-[:SUBCLASS_OF*0..]->(c)
                MATCH (o:Object)-[:RDF_TYPE]->(sub)
                RETURN DISTINCT o
            """, u=class_uri)
            return [r["o"] for r in res]

    def update_class(self, class_uri: str, title: str, description: str):
        return self.repo.update_node(class_uri, {"title": title, "description": description})

    def create_class(self, title: str, description: str, parent_uri: str = None):
        node = self.repo.create_node({
            "labels": ["Class"],
            "properties": {"title": title, "description": description}
        })

        if parent_uri:
            self.repo.create_arc(node.uri, parent_uri, {"labels": ["SUBCLASS_OF"], "properties": {}})

        return node

    def add_class_parent(self, parent_uri: str, target_uri: str):
        with self.repo.driver.session() as session:
            session.run("""
                MATCH (p:Class {uri:$p}), (c:Class {uri:$c})
                MERGE (c)-[:SUBCLASS_OF]->(p)
            """, p=parent_uri, c=target_uri)
        return "OK"

    def delete_class(self, class_uri: str):
        subtree = self._subtree_class_uris(class_uri)
        if not subtree:
            return False

        with self.repo.driver.session() as session:
            rels = session.run("""
                MATCH (c:Class)-[:DOMAIN]->(op:ObjectProperty)
                WHERE c.uri IN $uris
                RETURN DISTINCT op.rel_type as rt
            """, uris=subtree)

            rts = [r["rt"] for r in rels if r["rt"]]
            for rt in rts:
                session.run(f"""
                    MATCH (:Object)-[r:{rt}]->(:Object)
                    DELETE r
                """)
                
            session.run("""
                MATCH (o:Object)-[:RDF_TYPE]->(c:Class)
                WHERE c.uri IN $uris
                DETACH DELETE o
            """, uris=subtree)

            session.run("""
                MATCH (c:Class)-[:DOMAIN]->(p)
                WHERE c.uri IN $uris AND (p:DatatypeProperty OR p:ObjectProperty)
                DETACH DELETE p
            """, uris=subtree)

            session.run("""
                MATCH (c:Class)
                WHERE c.uri IN $uris
                DETACH DELETE c
            """, uris=subtree)

        return True

    def add_class_attribute(self, class_uri: str, attr_name: str):
        dp = self.repo.create_node({
            "labels": ["DatatypeProperty"],
            "properties": {"title": attr_name, "description": ""}
        })

        self.repo.create_arc(class_uri, dp.uri, {"labels": ["DOMAIN"], "properties": {}})

        return dp

    def delete_class_attribute(self, datatype_property_uri: str):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class)-[:DOMAIN]->(d:DatatypeProperty {uri:$u})
                RETURN c.uri as cu, d.title as title
            """, u=datatype_property_uri).single()

            if not rec:
                return False

            cu = rec["cu"]
            title = rec["title"]
            subtree = self._subtree_class_uris(cu)
            
            session.run("""
                MATCH (o:Object)-[:RDF_TYPE]->(c:Class)
                WHERE c.uri IN $uris
                SET o[$key] = null
            """, uris=subtree, key=title)

        self.repo.delete_node_by_uri(datatype_property_uri)
        return True

    def add_class_object_attribute(self, class_uri: str, attr_name: str, range_class_uri: str):
        op_uri = self.repo.generate_random_string()
        rel_type = self._tail_from_uri(op_uri)

        op = self.repo.create_node({
            "labels": ["ObjectProperty"],
            "properties": {"uri": op_uri, "title": attr_name, "rel_type": rel_type, "description": ""}
        })

        self.repo.create_arc(class_uri, op.uri, {"labels": ["DOMAIN"], "properties": {}})

        self.repo.create_arc(op.uri, range_class_uri, {"labels": ["RANGE"], "properties": {}})

        return op

    def delete_class_object_attribute(self, object_property_uri: str):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (op:ObjectProperty {uri:$u})
                RETURN op.rel_type as rt
            """, u=object_property_uri).single()

            if not rec or not rec["rt"]:
                return False

            rt = rec["rt"]

            session.run(f"""
                MATCH (:Object)-[r:{rt}]->(:Object)
                DELETE r
            """)

        self.repo.delete_node_by_uri(object_property_uri)
        return True

    def get_object(self, object_uri: str):
        return self.repo.get_node_by_uri(object_uri)

    def delete_object(self, object_uri: str):
        return self.repo.delete_node_by_uri(object_uri)

    def collect_signature(self, class_uri: str):
        with self.repo.driver.session() as session:
            parents = session.run("""
                MATCH (c:Class {uri:$u})
                MATCH (c)-[:SUBCLASS_OF*0..]->(p:Class)
                RETURN DISTINCT p.uri as pu
            """, u=class_uri)
            puris = [r["pu"] for r in parents if r["pu"]]

            dps = session.run("""
                MATCH (c:Class)-[:DOMAIN]->(d:DatatypeProperty)
                WHERE c.uri IN $uris
                RETURN DISTINCT d.title as t
            """, uris=puris)

            ops = session.run("""
                MATCH (c:Class)-[:DOMAIN]->(op:ObjectProperty)-[:RANGE]->(rc:Class)
                WHERE c.uri IN $uris
                RETURN DISTINCT op.title as t, op.rel_type as rt, rc.uri as rcu
            """, uris=puris)

            dt = [r["t"] for r in dps if r["t"]]

            ot = []
            for r in ops:
                ot.append({"title": r["t"], "rel_type": r["rt"], "range_class_uri": r["rcu"]})

            return {"datatype": dt, "object": ot}

    def create_object(self, class_uri: str, title: str, description: str, values=None, links=None):
        values = values or {}
        links = links or {}

        sig = self.collect_signature(class_uri)
        allowed_dt = set(sig["datatype"])
        allowed_rel = {o["rel_type"]: o["range_class_uri"] for o in sig["object"]}

        obj = self.repo.create_node({
            "labels": ["Object"],
            "properties": {"title": title, "description": description}
        })

        self.repo.create_arc(obj.uri, class_uri, {"labels": ["RDF_TYPE"], "properties": {}})

        fv = {k: v for k, v in values.items() if k in allowed_dt}
        if fv:
            self.repo.update_node(obj.uri, fv)

        with self.repo.driver.session() as session:
            for rt, targets in links.items():
                if rt not in allowed_rel:
                    continue
                for target_uri in targets:
                    session.run(f"""
                        MATCH (a:Object {{uri:$a}}), (b:Object {{uri:$b}})
                        CREATE (a)-[:{rt}]->(b)
                    """, a=obj.uri, b=target_uri)

        return obj

    def update_object(self, object_uri: str, values=None, links=None):
        values = values or {}
        links = links or {}

        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (o:Object {uri:$u})-[:RDF_TYPE]->(c:Class)
                RETURN c.uri as cu
            """, u=object_uri).single()
            if not rec:
                return None
            class_uri = rec["cu"]

        sig = self.collect_signature(class_uri)
        allowed_dt = set(sig["datatype"])
        allowed_rel = {o["rel_type"]: o["range_class_uri"] for o in sig["object"]}

        fv = {k: v for k, v in values.items() if k in allowed_dt}
        if fv:
            self.repo.update_node(object_uri, fv)

        with self.repo.driver.session() as session:
            for rt, targets in links.items():
                if rt not in allowed_rel:
                    continue

                session.run(f"""
                    MATCH (a:Object {{uri:$u}})-[r:{rt}]->(:Object)
                    DELETE r
                """, u=object_uri)

                for target_uri in targets:
                    session.run(f"""
                        MATCH (a:Object {{uri:$a}}), (b:Object {{uri:$b}})
                        CREATE (a)-[:{rt}]->(b)
                    """, a=object_uri, b=target_uri)

        return "OK"

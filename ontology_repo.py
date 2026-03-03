from main import Neo4jRepository


class OntologyRepository:
    def __init__(self, repo: Neo4jRepository):
        self.repo = repo

    def _tail_from_uri(self, uri):
        return uri.rsplit("/", 1)[-1]

    def _subtree_class_uris(self, class_uri):
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


    def get_class(self, class_uri):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class {uri:$u})
                RETURN c
            """, u=class_uri).single()
            return rec["c"] if rec else None

    def get_class_parents(self, class_uri):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})-[:SUBCLASS_OF*1..]->(p:Class)
                RETURN DISTINCT p
            """, u=class_uri)
            return [r["p"] for r in res]

    def get_class_children(self, class_uri):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})<-[:SUBCLASS_OF*1..]-(ch:Class)
                RETURN DISTINCT ch
            """, u=class_uri)
            return [r["ch"] for r in res]

    def get_class_objects(self, class_uri):
        with self.repo.driver.session() as session:
            res = session.run("""
                MATCH (c:Class {uri:$u})
                MATCH (sub:Class)-[:SUBCLASS_OF*0..]->(c)
                MATCH (o:Object)-[:RDF_TYPE]->(sub)
                RETURN DISTINCT o
            """, u=class_uri)
            return [r["o"] for r in res]

    def update_class(self, class_uri, title, description):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class {uri:$u})
                SET c.title=$t, c.description=$d
                RETURN c
            """, u=class_uri, t=title, d=description).single()
            return rec["c"] if rec else None

    def create_class(self, title, description, parent_uri=None):
        new_uri = self.repo.generate_random_string()
        with self.repo.driver.session() as session:
            if parent_uri:
                rec = session.run("""
                    MATCH (p:Class {uri:$p})
                    CREATE (c:Class {uri:$u, title:$t, description:$d})
                    CREATE (c)-[:SUBCLASS_OF]->(p)
                    RETURN c
                """, p=parent_uri, u=new_uri, t=title, d=description).single()
            else:
                rec = session.run("""
                    CREATE (c:Class {uri:$u, title:$t, description:$d})
                    RETURN c
                """, u=new_uri, t=title, d=description).single()
            return rec["c"] if rec else None

    def add_class_parent(self, parent_uri, target_uri):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (p:Class {uri:$p}), (c:Class {uri:$c})
                MERGE (c)-[:SUBCLASS_OF]->(p)
                RETURN c
            """, p=parent_uri, c=target_uri).single()
            return rec["c"] if rec else None

    def add_class_attribute(self, class_uri, attr_name):
        dp_uri = self.repo.generate_random_string()
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class {uri:$c})
                CREATE (d:DatatypeProperty {uri:$u, title:$t})
                CREATE (c)-[:DOMAIN]->(d)
                RETURN d
            """, c=class_uri, u=dp_uri, t=attr_name).single()
            return rec["d"] if rec else None

    def delete_class_attribute(self, datatype_property_uri):
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

            session.run("""
                MATCH (d:DatatypeProperty {uri:$u})
                DETACH DELETE d
            """, u=datatype_property_uri)

            return True

    def add_class_object_attribute(self, class_uri, attr_name, range_class_uri):
        op_uri = self.repo.generate_random_string()
        rel_type = self._tail_from_uri(op_uri)

        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class {uri:$c}), (r:Class {uri:$r})
                CREATE (op:ObjectProperty {uri:$u, title:$t, rel_type:$rel})
                CREATE (c)-[:DOMAIN]->(op)
                CREATE (op)-[:RANGE]->(r)
                RETURN op
            """, c=class_uri, r=range_class_uri, u=op_uri, t=attr_name, rel=rel_type).single()
            return rec["op"] if rec else None

    def delete_class_object_attribute(self, object_property_uri):
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

            session.run("""
                MATCH (op:ObjectProperty {uri:$u})
                DETACH DELETE op
            """, u=object_property_uri)

            return True

    def get_object(self, object_uri):
        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (o:Object {uri:$u})
                RETURN o
            """, u=object_uri).single()
            return rec["o"] if rec else None

    def delete_object(self, object_uri):
        with self.repo.driver.session() as session:
            session.run("""
                MATCH (o:Object {uri:$u})
                DETACH DELETE o
            """, u=object_uri)
            return True

    def collect_signature(self, class_uri):
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

    def create_object(self, class_uri, title, description, values=None, links=None):
        values = values or {}
        links = links or {}

        sig = self.collect_signature(class_uri)
        allowed_dt = set(sig["datatype"])
        allowed_rel = {o["rel_type"]: o["range_class_uri"] for o in sig["object"]}

        obj_uri = self.repo.generate_random_string()

        with self.repo.driver.session() as session:
            rec = session.run("""
                MATCH (c:Class {uri:$c})
                CREATE (o:Object {uri:$u, title:$t, description:$d})
                CREATE (o)-[:RDF_TYPE]->(c)
                RETURN o
            """, c=class_uri, u=obj_uri, t=title, d=description).single()

            if not rec:
                return None

            fv = {k: v for k, v in values.items() if k in allowed_dt}
            if fv:
                sets = []
                params = {"u": obj_uri}
                i = 0
                for k, v in fv.items():
                    i += 1
                    p = f"v{i}"
                    sets.append(f"o.`{k}` = ${p}")
                    params[p] = v

                session.run(f"""
                    MATCH (o:Object {{uri:$u}})
                    SET {", ".join(sets)}
                """, **params)

            for rt, targets in links.items():
                if rt not in allowed_rel:
                    continue
                for target_uri in targets:
                    session.run(f"""
                        MATCH (a:Object {{uri:$a}}), (b:Object {{uri:$b}})
                        CREATE (a)-[:{rt}]->(b)
                    """, a=obj_uri, b=target_uri)

            return rec["o"]

    def update_object(self, object_uri, values=None, links=None):
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

        with self.repo.driver.session() as session:
            fv = {k: v for k, v in values.items() if k in allowed_dt}
            if fv:
                sets = []
                params = {"u": object_uri}
                i = 0
                for k, v in fv.items():
                    i += 1
                    p = f"v{i}"
                    sets.append(f"o.`{k}` = ${p}")
                    params[p] = v

                session.run(f"""
                    MATCH (o:Object {{uri:$u}})
                    SET {", ".join(sets)}
                """, **params)

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

            rec2 = session.run("""
                MATCH (o:Object {uri:$u})
                RETURN o
            """, u=object_uri).single()

            return rec2["o"] if rec2 else None

    def delete_class(self, class_uri):
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
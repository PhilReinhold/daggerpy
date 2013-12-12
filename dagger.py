import ast
import sys
from collections import defaultdict
from recordtype import recordtype


class Node(object):
    _next_id = 0
    def __init__(self, op, srcs):
        self.id = Node._next_id
        Node._next_id += 1
        self.op, self.srcs = op, srcs
        self.annotate()
        self.canonicalize()

    def __repr__(self):
        scalar_s = "S" if self.scalar else "T"
        inv_s = "I" if self.inv else "V"
        srcs_s = "(%s)" % (",".join(str(s.id) for s in self.srcs))
        return '%s:(%s%s) <- %s%s' % (self.id, scalar_s, inv_s, self.op, srcs_s)

    def repr_tree(self, printed=None):
        if printed is None:
            printed = []
        stmts = []
        for s in self.srcs:
            if s not in printed:
                stmts.append(s.repr_tree(printed))
        if self not in printed:
            printed.append(self)
            stmts.append(str(self))
        return "\n".join(stmts)

    def __cmp__(self, other):
        return self.id - other.id

    @property
    def id_expr(self):
        return self.op, self.srcs

    def annotate(self):
        self.scalar = all(s.scalar for s in self.srcs) or self.op == 'tr'
        self.inv = all(s.inv for s in self.srcs)

        self.unary = len(self.srcs) == 1
        self.binary = len(self.srcs) == 2
        self.multivariance = self.binary and self.srcs[0].inv != self.srcs[1].inv
        if self.multivariance:
            self.inv_src = [s for s in self.srcs if s.inv][0]
            self.v_src = [s for s in self.srcs if not s.inv][0]
            self.associative = self.op in ('Add', 'Mult') and self.op == self.v_src.op
            self.inv_on_left = self.srcs == (self.inv_src, self.v_src)
        self.abelian = self.op == 'Add' or (
            self.op == 'Mult' and any(s.scalar for s in self.srcs)
        )

    def canonicalize(self):
        if self.abelian:
            self.srcs = min(self.srcs), max(self.srcs)

        if self.multivariance and self.associative and self.v_src.multivariance:
            i, vi, vv = self.inv_src, self.v_src.inv_src, self.v_src.v_src
            if self.inv_on_left == self.v_src.inv_on_left or self.v_src.abelian:
                if self.inv_on_left:
                    new_node = Node(self.op, (i, vi))
                    self.srcs = (new_node, vv)
                else:
                    new_node = Node(self.op, (vi, i))
                    self.srcs = (vv, new_node)
                new_node.scalar = i.scalar and vi.scalar
                new_node.inv = False

class NodeSet(dict):
    def __init__(self):
        dict.__init__(self)
        self.order = []

    def __missing__(self, key):
        n = Node(*key)
        if n.id_expr in self:
            n = self[n.id_expr]
        else:
            self.order.append(key)
        self[key] = self[n.id_expr] = n
        return n

    def __iter__(self):
        for k in self.order:
            yield self[k]

class Compiler(object):
    def __init__(self, string, scalars=None, invariants=None):
        self.string = string
        self.nodes = NodeSet()
        self.assignments = {}
        self.separated = False
        self.scalars = default(scalars, [])
        self.invariants = default(invariants, [])

        Node._next_id = 0

        # Do Everything
        self.module2node(ast.parse(string))

    def __repr__(self):
        if self.separated and self.inv_nodes:
            node_s = "------\n".join(
                "\n".join(str(t) for t in tl) for tl in (self.inv_nodes, self.v_nodes)
            )
        else:
            node_s = "\n".join(str(t) for t in self.nodes)

        node_s = list(self.assignments.values())[-1].repr_tree()

        return "\n".join([
            self.string,
            node_s, ""
        ])

    def dispatch(self, st):
        return {
            ast.Assign: self.assign2node,
            ast.UnaryOp: self.unary2node,
            ast.Attribute: self.attr2node,
            ast.BinOp: self.binary2node,
            ast.Name: self.name2node
        }[type(st)](st)

    def put_node(self, op, *srcs):
        n = self.nodes[(op, srcs)]
        return n

    def assign2node(self, st):
        self.assignments[st.targets[0].id] = self.dispatch(st.value)

    def attr2node(self, st):
        return self.put_node(st.attr, self.dispatch(st.value))

    def name2node(self, st):
        n = self.put_node(st.id)
        n.scalar = st.id in self.scalars
        n.inv = st.id in self.invariants
        return n

    def unary2node(self, st):
        return self.put_node(
            type(st.op).__name__,
            self.dispatch(st.operand)
        )

    def binary2node(self, st):
        return self.put_node(
            type(st.op).__name__,
            self.dispatch(st.left),
            self.dispatch(st.right)
        )
    
    def module2node(self, module):
        for stmt in module.body:
            self.dispatch(stmt)

            
def default(a, v):
    return a if a else v

def group_list(l, n):
    nr = len(l) % n
    rem = l[-nr:] if nr else []
    return zip(*[iter(l)]*n) + [tuple(rem)]
                
def dict_pprint(name, d):
    ds = ",\n\t".join(
        ", ".join("%s: %s" % i for i in group) for  group in group_list(d.items(),3)
    )
    return "%s{\n\t%s\n}" % (name,  ds)

if __name__ == "__main__":
    print "\n"
    #print Compiler('z = a*b + b*a')
    #print Compiler('z = a*b + b*a')
    #print Compiler('z = a*b + b*a', scalars=['a','b'])
    print Compiler('z = c*(a.hc*b + b.hc*a)*d', scalars=['c','d'], invariants=['c','d'])

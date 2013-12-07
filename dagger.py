import ast
import sys
from collections import defaultdict
from recordtype import recordtype

_curid = 0
def get_id():
    global _curid
    _curid += 1
    return _curid 

class tac(object):
    def __init__(self, op, srcs):
        self.op, self.srcs = op, srcs
        self.dst = get_id()
        self.dst_scalar, self.srcs_scalar = None, None

    def __repr__(self):
        return'%s <- %s%s' % (self.dst, self.op, self.srcs)

    @property
    def id(self):
        return self.op, self.srcs

    def annotate(self, scalar_refs):
        self.srcs_scalar = [s in scalar_refs for s in self.srcs]
        if self.op in ('Mult', 'Add'):
            self.dst_scalar = all(self.srcs_scalar)
        else:
            self.dst_scalar = self.srcs_scalar[0]

        self.validate()
        self.canonicalize()

    def validate(self):
        if self.op not in ('Add', 'Mult', 'USub', 'sqrt', 'hc', 'tr', 'negate'):
            raise Exception('Operation %s not yet supported' % self.op)
        if self.op is 'Add' and self.srcs_scalar[0] != self.srcs_scalar[1]:
            raise Exception('Trying to add scalar to operator')
        if self.op is 'sqrt' and not self.srcs_scalar[0]:
            raise Exception('Operator square root not supported')
        if self.op is 'tr' and self.self.srcs_scalar[0]:
            raise Exception('Trying to take trace of scalar')

    def canonicalize(self):
        abelian = self.op == 'Add'
        abelian = abelian or (self.op == 'Mult' and any(self.srcs_scalar))
        if abelian:
            self.srcs = min(self.srcs), max(self.srcs)

    def rewrite(self, rwdict):
        self.srcs = tuple(rwdict.get(s, s) for s in self.srcs)

class taccer(object):
    def __init__(self, string, scalars=None):
        self.tacs = []
        self.refd = defaultdict(get_id)
        self.scalars = scalars if scalars else []
        self.module2tac(ast.parse(string))

    def __repr__(self):
        s = "Refs: %s\n" % dict(self.refd)
        return s + "\n".join(str(t) for t in self.tacs)

    def dispatch(self, st):
        return {
            ast.Assign: self.assign2tac,
            ast.UnaryOp: self.unary2tac,
            ast.Attribute: self.attr2tac,
            ast.BinOp: self.binary2tac,
            ast.Name: lambda x: self.refd[x.id],
        }[type(st)](st)

    def push(self, op, *srcs):
        t = tac(op, srcs)
        self.tacs.append(t)
        return t.dst

    def assign2tac(self, st):
        self.refd[st.targets[0].id] = self.dispatch(st.value)

    def attr2tac(self, st):
        return self.push(st.attr, self.dispatch(st.value))

    def unary2tac(self, st):
        return self.push(
            type(st.op).__name__,
            self.dispatch(st.operand)
        )

    def binary2tac(self, st):
        return self.push(
            type(st.op).__name__,
            self.dispatch(st.left),
            self.dispatch(st.right)
        )
    
    def module2tac(self, module):
        for stmt in module.body:
            self.dispatch(stmt)

        self.annotate()
        self.sub_exp_elim()

    def annotate(self):
        annotations = {}
        scalar_refs = [ref for name, ref in self.refd.items() if name in self.scalars]
        for t in self.tacs:
            t.annotate(scalar_refs)
            if t.dst_scalar:
                scalar_refs.append(t.dst)

    def sub_exp_elim(self):
        newtacs = []
        seen = {}
        rw = {}
        for t in self.tacs:
            t.rewrite(rw)
            if t.id in seen:
                rw[t.dst] = seen[t.id]
            else:
                seen[t.id] = t.dst
                newtacs.append(t)
        self.tacs = newtacs
               
if __name__ == "__main__":
    print taccer('z = a*b + b*a')
    print taccer('z = a*b + b*a', scalars=['a','b'])
    print taccer('z = c*(a*b + b*a)*d', scalars=['a','b'])

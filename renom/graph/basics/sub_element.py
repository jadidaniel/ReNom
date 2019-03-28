import numpy as np
import renom as rm
from renom.graph.core import operation, GraphMultiStorage, operational_element, UserGraph, GraphFactory
from renom.utils import broad_cast, cu_broad_cast


class sub_forward(operation):

    name = 'Sub (F)'

    def __init__(self):
        self._a = None
        self._b = None

    def setup(self, inputs):
        a = inputs[0]['y']
        b = inputs[1]['y']
        assert len(a) == len(b)
        self.gpus = a.gpus
        self._a = a
        self._b = b
        output_shape = (np.zeros(a.shape) + np.zeros(b.shape)).shape
        self._c = GraphMultiStorage(shape=output_shape, gpus=self.gpus)
        self._vars = {'a': a, 'b': b, 'y': self._c}

    def perform(self):
        for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
            rm.cuda.cusub(self._a[gpu], self._b[gpu], self._c[gpu], handle)


class sub_forward_cpu(sub_forward):

    def perform(self):
        a = self._a['cpu']
        b = self._b['cpu']
        self._c['cpu'] = a - b


class sub_backward(operation):

    name = 'Sub (B)'

    def __init__(self, associated_forward, key):
        self._fwd_op = associated_forward
        self._key = key

    def setup(self, inputs):
        self._inputs = inputs[0]['y']
        key = self._key
        key_value = self._fwd_op.get_key(key)
        gpus = key_value.gpus
        output_shape = key_value.shape
        outputs = GraphMultiStorage(shape=output_shape, gpus=gpus, initializer=None)
        self.gpus = gpus
        self._fwd_in = key_value
        self._vars = {'y': outputs, 'dy': outputs, id(key_value): outputs}
        self._outputs = outputs

    def perform(self):
        for i, (gpu, handle) in enumerate(rm.cuda.RenomHandlers(self.gpus)):
            if self._key == "a":
                dy = self._inputs[gpu]
            elif self._key == "b":
                dy = -1 * self._inputs[gpu]
            else:
                # TODO: Set exception
                raise Exception()

            if self._fwd_in[gpu].shape == dy.shape:
                dy = dy
            else:
                dy = cu_broad_cast(self._fwd_in[gpu], dy)
            self._outputs[gpu] = dy


class sub_backward_cpu(sub_backward):

    def perform(self):
        fwd_in = self._fwd_in['cpu']
        if self._key == "a":
            dy = self._inputs['cpu']
        elif self._key == "b":
            dy = -self._inputs['cpu']
        else:
            raise Exception()

        if fwd_in.shape == dy.shape:
            self._outputs['cpu'] = dy
        else:
            self._outputs['cpu'] = broad_cast(fwd_in, dy)


class SubElement(UserGraph):

    _name = 'Sub Element'

    def __init__(self, previous_elements=None):

        fwd_op = sub_forward() if rm.is_cuda_active() else sub_forward_cpu()
        bwd_ops = [sub_backward(fwd_op, 'a') if rm.is_cuda_active() else sub_backward_cpu(fwd_op, 'a'),
                   sub_backward(fwd_op, 'b') if rm.is_cuda_active() else sub_backward_cpu(fwd_op, 'b')]
        super().__init__(fwd_op, bwd_ops, previous_elements)


class Sub(GraphFactory):

    def connect(self, lhs, rhs):
        return SubElement([lhs, rhs])


def _sub(self, other):
    ret = SubElement([self, other])
    return ret


UserGraph.__sub__ = _sub
UserGraph.__isub__ = _sub
UserGraph.__rsub__ = _sub

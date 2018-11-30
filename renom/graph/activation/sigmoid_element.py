import renom as rm
from renom.graph.core import learnable_graph_element, operation, GraphFactory, graph_variable, multi_gpu_variable
import renom.utility.initializer as init
import numpy as np

class sigmoid_forward(operation):

  def setup(self, inputs, storage):
    inputs = inputs[0]['y']
    gpus = inputs.gpus
    self.gpus = gpus
    outs = multi_gpu_variable(shape = inputs.shape, gpus = gpus)
    self._vars = { 'y' : outs}
    self._inputs = inputs
    self._outputs = outs

  def perform(self):
    for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
      rm.cuda.cusigmoid(self._inputs[gpu], self._outputs[gpu])

class sigmoid_forward_cpu(sigmoid_forward):

  def perform(self):
    x = self._inputs['cpu']
    ret = 1. / (1. + np.exp(-x))
    self._outputs['cpu'] = ret

class sigmoid_backward(operation):

  def __init__(self, associated_forward):
    self._fwd_op = associated_forward

  def setup(self, inputs, storage):
    inputs = inputs[0]['y']
    gpus = inputs.gpus
    self.gpus = gpus
    outs = multi_gpu_variable(shape = inputs.shape, gpus = gpus)
    self._vars = { 'y' : outs, id(self._fwd_op._inputs) : outs}
    self._fwd_out = self._fwd_op._outputs
    self._inputs = inputs
    self._outputs = outs

  def perform(self):
    for gpu, handle in rm.cuda.RenomHandlers(self.gpus):
      rm.cuda.cumul(self._fwd_out[gpu], -1, self._outputs[gpu], handle)
      rm.cuda.cuadd(self._outputs[gpu], 1, self._outputs[gpu], handle)
      rm.cuda.cumul(self._fwd_out[gpu], self._outputs[gpu], self._outputs[gpu], handle)
      rm.cuda.cumul(self._inputs[gpu], self._outputs[gpu], self._outputs[gpu], handle)

class sigmoid_backward_cpu(sigmoid_backward):

  def perform(self):
    dy = self._inputs['cpu']
    y = self._fwd_out['cpu']
    ret = y * (1. - y) * dy
    self._outputs['cpu'] = ret


class SigmoidElement(learnable_graph_element):

  has_back = True

  def __init__(self, previous_elements = None):
    fwd_op = sigmoid_forward() if rm.is_cuda_active() else sigmoid_forward_cpu()
    bwd_ops = [ sigmoid_backward(fwd_op) if rm.is_cuda_active() else sigmoid_backward_cpu(fwd_op) ]
    super().__init__(forward_operation = fwd_op, backward_operations = bwd_ops, previous_elements = previous_elements)

class SigmoidGraphElement(GraphFactory):

  def __init__(self):
    super().__init__()

  def connect(self, other):
    ret = SigmoidElement(previous_elements = other)
    return ret
"""
This module holds layers to build up a neural network.
"""
from __future__ import absolute_import, division, print_function

import abc
import sys
import copy

import tensorflow as tf

from ..utils import glog as log
from .common import GLOBAL_STEP, global_var_scope
from .common import (
    TRAIN_SUMMARY_COLLECTION,
    VALID_SUMMARY_COLLECTION,
    SPARSITY_SUMMARY_SUFFIX
)


class Block(object):
    """
    Abstract class for an arbitrary block.

    It models the general data processing process. The behavior of a block is
    supposed to take arbitrary number of inputs and output arbitrary number of
    outputs. `Source`, `Sensor`, `ProcessingLayer`, `LossLayer` and
    `ProcessingSystem` etc are all sub-classes of this class.

    A `Block` should try to implement most of its functionality only with what
    it owns, and ask for communication(which in implementation is to provide
    interfaces) as little as possible.

    Outputs of a block is in form of properties. `Block` has an abstract
    property data which sub-class should implement to provide the processed
    outputs.

    `setup` is the interface for any containers, such as a `Brain` class, that
    hold this block, to call to set up this block. It is a wrapper for the
    actual abstract `_setup` method which should be implemented by concrete
    layer, and other pre-setup and post-setup methods.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, do_summary=True, name=None, bag=None):
        """
        Create a layer and name it.

        Args:
            name: str
                The name of the layer. It also serves as the name scope of this
                layer in tensorflow. If `None`, the default name provided by
                Tensorflow will be used.
            do_summary: Boolean
                Whether to do summary on blocks contained. If True, outputs of
                this `Block` would be added to tensorflow summary.
            bag: supposed to be a dict
                A dictionary that holds any further ad hoc information one
                wants to keep in this block, such as a list of filters you want
                to visualize later.
        """
        if not name:
            log.error("{}'s `name` argument cannot be None! It serves as an"
                      " identifier, also is used in visualization and"
                      " summary etc.".format(type(self)))
            sys.exit(1)

        self.name = name
        self.do_summary = do_summary
        log.info("{} has bag: {}".format(name, bag))
        self.bag = bag

        # Boolean flag to indicate whether this layer has been built before. It
        # is used for determining whether we should share variables of this
        # layer later in `setup`. We need this for creating validation brain or
        # others network structures need sharing learnable variables.  It is
        # also useful to other things, such as determining whether to add
        # tensorboard summary etc.
        self.is_setup = None

    @abc.abstractmethod
    def data(self):
        """
        An abstract method to enforce all sub-classes to provide their
        processed data through this interface.

        A tentative design:

            ## Single Output Block
            If a block only has one output, the data method just returns the
            data tensor, optionally makes the method a property;

            ## Multiple Output Block
            If a block has multiple outputs, a tentative design is to return a
            dict or a list. The further usage of the outputs takes the output
            as their input by the name of the tensor.

            How the naming creation and lookup has not been figured out
            yet. The name of the outputs should have the name of the block as
            its prefix. So attention is needed to take care of the things that
            added by tensorflow automatically. The retrieve of outputs could
            make use of the collection mechanism provided by tensorflow.
        """
        raise NotImplementedError("Each concrete block needs to implement this"
                                  " method to provide an interface to offer"
                                  " data!")
        sys.exit()

    def setup(self, *args, **kwargs):
        """
        Common wrapper of all kinds of layers' `_setup` to do stat and
        visualization related logistics. If `_setup` has any output, it would
        be returned.

        A `Block` could be set up any times one wants. Each time it would build
        computational graph to process input offered this time, and any
        variables are shared. For now, a second time setup only happens when
        building validation brain.

        Args:
            All arguments will be passed to the actual `_setup` function.
        """
        with tf.variable_scope(self.name, reuse=self.is_setup):
            self._pre_setup()
            if not self.is_setup:
                self._pre_setup_shared()
            self._setup(*args, **kwargs)
            self._post_setup()
            if not self.is_setup:
                self._post_setup_shared()

        self.is_setup = True

    def _pre_setup(self):
        """
        Some setting won't be determined till the time to call setup. This is
        the place to set up the those settings. See `moving_averages` of
        `ProcessingLayer` for an example.
        """
        pass

    def _pre_setup_shared(self):
        """
        This is the place to do pre-setups on shared components. This method
        would only be called at the first time this block is setup. Refer to
        `_pre_setup` to see what pre-setups is for.
        """
        pass

    def _post_setup_shared(self):
        """
        This is the place to do post-setups on shared components. This method
        would only be called at the first time this block is setup. Refer to
        `_post_setup` to see what post-setups is for.
        """
        pass

    def _post_setup(self):
        """
        Some setting cannot be set up until the whole setup has been done. This
        is the place to set up those settings. See `moving_averages` of
        `ProcessingLayer` for an example.
        """
        pass

    @abc.abstractmethod
    def _setup(self):
        """
        An abstract method that must be overrided.
        """
        raise NotImplementedError('Each sub-layer needs to implement this'
                                  'method to process data!')
        sys.exit()


class ProcessingLayer(Block):
    """
    An abstract layer for data processing layer in the brain.

    A `ProcessingLayer` is nothing if it does not process data. So every
    sub-class of `ProcessingLayer` should possess a `data` property as
    interface to provide the data it processes.

    For now, all processing layers only have one output, and provide it via
    property `data`. So it overrides the `data` method of `Block`.
    """
    def __init__(self, moving_average_decay=None, **kwargs):
        """
        Args:
            moving_average_decay: A fraction. If `None`, When the parameters of
                this layer is being shared, the shared paras should be
                the current value of the paras. If has a value, it would be
                used in `tf.train.ExponentialMovingAverage`. Then the shared
                value would be the moving average.
        """
        super(ProcessingLayer, self).__init__(**kwargs)

        assert moving_average_decay is None or \
            moving_average_decay >= 0.5 and moving_average_decay < 1, \
            ("Invalid moving_average_decay value {}. Should be None or"
             " between [0.5, 1]".format(moving_average_decay))
        self.moving_average_decay = moving_average_decay

        # Bookkeeping all variables.
        self.var_list = []

        # A Boolean flag to indicate whether this block is in validation mode.
        self.is_val = False

    def get_val_copy(self):
        """
        Get a copy for validation.

        Since a processing layer is learned, it has to be taken out for
        evaluation from time to time.
        """
        val_copy = self.get_copy()
        val_copy.set_val()
        return val_copy

    def get_copy(self):
        return copy.copy(self)

    def set_val(self):
        self.is_val = True

    def _pre_setup_shared(self):
        # Moving averages are supposed be shared so it would only be set up
        # once.
        if self.moving_average_decay:
            # We pass current training step to moving average to speed up
            # updates moving average of variables at the beginning of the
            # training since moving average is useful only later.
            with tf.variable_scope(global_var_scope, reuse=True):
                step = tf.get_variable(GLOBAL_STEP)
            self.moving_averages = tf.train.ExponentialMovingAverage(
                self.moving_average_decay, step)

    def _post_setup(self):
        if self.do_summary:
            log.info("Do tensorboard summary on outputs of {}".format(
                self.name))
            collection_to_add = VALID_SUMMARY_COLLECTION if self.is_val \
                else TRAIN_SUMMARY_COLLECTION
            if self.data is not None:
                self._data_summary(self.data, collection_to_add)
            if self.loss is not None:
                tf.scalar_summary(self.loss.op.name,
                                  self.loss,
                                  collections=[collection_to_add])

    def _data_summary(self, data, collection=TRAIN_SUMMARY_COLLECTION):
        """
        Helper function to do statistical summary on the bundle of data.

        Args:
            collection: which op collection to add to. It should be one of
                TRAIN_SUMMARY_COLLECTION or VALID_SUMMARY_COLLECTION from
                akid.core.common.
        """
        assert collection is TRAIN_SUMMARY_COLLECTION or \
            collection is VALID_SUMMARY_COLLECTION, \
            "{} is not one of those defined in common.py. Some thing is wrong"
        tf.histogram_summary(data.op.name + '/activations',
                             data,
                             collections=[collection])
        tf.scalar_summary(data.op.name + '/' + SPARSITY_SUMMARY_SUFFIX,
                          tf.nn.zero_fraction(data),
                          collections=[collection])

    def _post_setup_shared(self):
        # Maintain moving averages of variables.
        if self.moving_average_decay and len(self.var_list) is not 0:
            self.moving_averages_op = self.moving_averages.apply(self.var_list)
            with tf.control_dependencies([self.moving_averages_op]):
                self._data = tf.identity(
                    self._data,
                    # We add one underscore to the original data's name to the
                    # has-to existing identity data due to the need of control
                    # dependency.
                    name=self._data.op.name.split('/')[-1] + "_")

        if self.do_summary:
            log.info("Do tensorboard summary on variables of {}".format(
                self.name))
            for var in self.var_list:
                self._var_summary(var.op.name, var)
        if self.moving_average_decay:
            for var in self.var_list:
                var_average = self.moving_averages.average(var)
                self._var_summary(var.op.name + "_average", var_average)

    def _var_summary(self, tag, var):
        if len(var.get_shape().as_list()) is 0:
            tf.scalar_summary(tag, var, collections=[TRAIN_SUMMARY_COLLECTION])
        else:
            tf.histogram_summary(tag,
                                 var,
                                 collections=[TRAIN_SUMMARY_COLLECTION])

    @property
    def data(self):
        """
        All sub-class `ProcessingLayer` should save the processed data to
        `_data`.
        """
        if hasattr(self, "_data"):
            return self._data
        else:
            return None

    @property
    def loss(self):
        """
        Each `ProcessingLayer` could optionally associated it with a loss. A
        `ProcessingLayer` is the smallest unit in the hierarchical data
        processing system. Since for every data processing system, it would has
        a loss, which is the purpose of its existence, so a `ProcessingLayer`
        layer also could have a loss.

        All sub-classes should save loss to `_loss`.
        """
        if hasattr(self, "_loss"):
            return self._loss
        else:
            return None

    def _get_variable(self, name, shape, initializer):
        """
        Allocate or retrieve tensorflow variables. If the variable has already
        existed, depending on `moving_average_decay`'s value, moving average of
        it(when `moving_average_decay` has a value) or the original
        variable(when `moving_average_decay` is None) would be returned. Refer
        to `tf.get_variable()` to the details of a shared variable in
        tensorflow.
        """
        var = tf.get_variable(name, shape, initializer=initializer)

        if self.is_setup:
            if self.moving_average_decay:
                log.debug("Use moving average of paras {}".format(
                    var.op.name))
                var = self.moving_averages.average(var)
            else:
                log.debug("Reuse paras {}".format(var.op.name))
        else:
            # Append it to the var list, do moving average later in
            # `_post_setup`.
            self.var_list.append(var)

        return var

from analysis.abstract_interpretation import AbstractInterpretation
import parse.parse_format_text as parse_format_text
import math
import copy
import warnings
from solver import Range, Solver, Array
import numpy as np
import z3
from utils import OVERFLOW_D, UNDERFLOW_D, OVERFLOW_LIMIT, UNDERFLOW_LIMIT
from utils import resolve_type
from itertools import combinations_with_replacement, product

turn_on_bool = False


def real_size(a, b):
    if str(a) == "?" and str(b) == "?":
        raise AssertionError("cannot infer ? size")
    elif str(a) == "?":
        return int(b)
    else:
        return int(a)


class InferValue:
    @staticmethod
    def add(args: list, node):
        assert len(args) == 2
        if args[0].value is None or args[1].value is None:
            return None
        if isinstance(args[0].value, Range) or isinstance(args[1].value, Range):
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            return Range(left=x.left + y.left, right=x.right + y.right)
        else:
            return args[0].value + args[1].value

    @staticmethod
    def addn(args: list, node):
        assert len(args) > 0
        if len(args) == 1:
            return args[0].value
        else:
            s = InferValue.add([args[0], args[1]], node)
            for i in range(2, len(args)):
                s = InferValue.add([AbstractInterpretation(value=s), args[i]], node)
            return s

    @staticmethod
    def all(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), True,
                                z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), False, True)),
                     right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), False,
                                 z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), True, True)))

    @staticmethod
    def any(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), True,
                                z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), False, True)),
                     right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), False,
                                 z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), True, True)))

    @staticmethod
    def argmax(args: list, node):
        assert len(args) == 2
        try:
            return Range(left=0, right=int(args[0].size[int(args[1].value)]) - 1)
        except:
            value = Range(left=0, right=Solver.add_variable("argmax_R", 3))
            return value, value.left <= value.right

    @staticmethod
    def assign(args: list, node):
        assert len(args) == 2
        if args[0].value is None:
            return args[1].value
        else:
            return args[0].value
        
    def assignadd(args: list, node):
        k = Solver.add_variable("assignadd", 3)
        y = InferValue.expanddims([args[1]], node)
        args[0].value.left = k * y.left
        args[0].value.right = k * y.right
        return args[0].value, k > 0

    @staticmethod
    def avgpool(args: list, node):
        assert len(args) == 1
        return InferValue.expanddims(args, node)

    @staticmethod
    def batchmatmul(args: list, node):
        assert len(args) == 2
        x = copy.deepcopy(args[0])
        y = copy.deepcopy(args[1])
        x.size = x.size[1:]
        y.size = y.size[1:]
        return InferValue.matmul([x, y], node)

    @staticmethod
    def biasadd(args: list, node):
        assert len(args) == 2 and len(args[1].size) == 1 and (
                str(args[0].size[-1]) == "?" or str(args[1].size[0]) or args[0].size[-1] == args[1].size[0])
        # ind = real_size(args[0].size[-1], args[1].size[0])
        return Range(left=args[0].value.left + args[1].value.left,
                     right=args[0].value.right + args[1].value.right)

    @staticmethod
    def cast(args: list, node):
        assert len(args) == 1
        attrs = node.attr
        if int(attrs['SrcT'].type) in [3] and int(attrs['DstT'].type) in [1]:
            if isinstance(args[0].value, Range):
                value = Range(name="cast", dtype=1)
                return value, z3.And(value.left == args[0].value.left, value.right == args[0].value.right)
            else:
                try:
                    return float(args[0].value)
                except:
                    return Range(left=float(np.min(args[0].value)), right=float(np.max(args[0].value)))
        elif int(attrs['SrcT'].type) in [10] and int(attrs['DstT'].type) in [1]:
            return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), 0,
                                    z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), 1, 0)),
                         right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), 0,
                                     z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), 1, 1)))
        elif int(attrs['SrcT'].type) in [10] and int(attrs['DstT'].type) in [3]:
            return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), 0,
                                    z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), 1, 0)),
                         right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), 0,
                                     z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), 1, 1)))
        elif int(attrs['SrcT'].type) in [1] and int(attrs['DstT'].type) in [10]:
            return Range(left=z3.If(z3.And(args[0].value.left == 0, args[0].value.right == 0), True,
                                    z3.If(z3.And(args[0].value.left == 0, args[0].value.right == 0), False, True)),
                         right=z3.If(z3.And(args[0].value.left == 0, args[0].value.right == 0), False,
                                     z3.If(z3.And(args[0].value.left == 0, args[0].value.right == 0), True, True)))
        elif int(attrs['SrcT'].type) in [9] and int(attrs['DstT'].type) in [3]:
            return args[0].value
        elif int(attrs['SrcT'].type) in [3] and int(attrs['DstT'].type) in [9]:
            return args[0].value
        elif int(attrs['SrcT'].type) in [1] and int(attrs['DstT'].type) in [3]:
            return InferValue.floor(args, node)
        else:
            raise NotImplementedError("%s -> %s not implemented!" % (attrs['SrcT'].type, attrs['DstT'].type))

    @staticmethod
    def clipbyvalue(args: list, node):
        assert len(args) == 3
        if isinstance(args[0].value, Range):
            value = Range(name="clipbyvalue", dtype=args[0].dtype)
            return value, z3.And(Solver.max(value.left, [args[0].value.left,
                                                         args[1].value if not isinstance(args[1].value, Range) else
                                                         args[1].value.left]),
                                 Solver.min(value.right, [args[0].value.right,
                                                          args[2].value if not isinstance(args[2].value, Range) else
                                                          args[2].value.right]))
        else:
            return min(max(args[0].value, args[1].value), args[2].value)

    @staticmethod
    def concatv2(args: list, node):
        return InferValue.pack(args[:-1], node)

    @staticmethod
    def const(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, node.op.lower())(node)

    @staticmethod
    def conv2d(args: list, node):
        assert len(args) == 2
        ind = 1
        for x in args[1].size[:-1]:
            ind *= int(x)
        value = Range(name="conv2d", dtype=args[0].dtype)
        ends = [args[0].value.left * args[1].value.left * ind, args[0].value.left * args[1].value.right * ind,
                args[0].value.right * args[1].value.left * ind, args[0].value.right * args[1].value.right * ind]
        return value, z3.And(Solver.min(value.left, ends),
                             Solver.max(value.right, ends))

    @staticmethod
    def depthwiseconv2dnative(args: list, node):
        assert len(args) == 2
        ind = 1
        for x in args[1].size[:2]:
            ind *= int(x)
        value = Range(name="depthwiseconv2dnative", dtype=args[0].dtype)
        ends = [args[0].value.left * args[1].value.left * ind, args[0].value.left * args[1].value.right * ind,
                args[0].value.right * args[1].value.left * ind, args[0].value.right * args[1].value.right * ind]
        return value, z3.And(Solver.min(value.left, ends),
                             Solver.max(value.right, ends))

    @staticmethod
    def dynamicstitch(args: list, node):
        assert len(args) % 2 == 0
        datas = args[len(args) // 2:]
        return InferValue.pack(datas, node)

    @staticmethod
    def enter(args: list, node):
        assert len(args) == 1
        return args[0].value

    @staticmethod
    def equal(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if not isinstance(args[0].value, Range) and not isinstance(args[1].value, Range):
            return np.equal(args[0].value, args[1].value)
        else:
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            condition = z3.And(x.left == y.left, x.right == y.right, x.left == x.right)
            return Range(left=z3.If(condition, False, True), right=z3.If(condition, True, True))

    @staticmethod
    def exit(args: list, node):
        return InferValue.identity(args, node)

    @staticmethod
    def expanddims(args: list, node):
        return args[0].value if isinstance(args[0].value, Range) else Range(left=resolve_type(np.min(args[0].value)),
                                                                            right=resolve_type(np.max(args[0].value)))

    @staticmethod
    def fill(args: list, node):
        assert len(args) == 2
        return args[1].value

    @staticmethod
    def floor(args: list, node):
        assert len(args) == 1
        if isinstance(args[0].value, Range):
            value = Range(name="floor", dtype=args[0].dtype)
            return value, z3.And(
                [value.left >= args[0].value.left, value.left < args[0].value.left + 1,
                 value.right >= args[0].value.right,
                 value.right < args[0].value.right + 1])
        else:
            return np.floor(args[0].value)

    @staticmethod
    def fusedbatchnorm(args: list, node):
        assert len(args) == 5
        # x, scale, offset, mean, variance
        epsilon = float(node.attr['epsilon'].f)
        is_training = node.attr["is_training"].b

        x = InferValue.expanddims([args[0]], node)
        mean = InferValue.expanddims([args[1]], node)
        variance = InferValue.expanddims([args[2]], node)
        offset = args[3].value
        scale = args[4].value + epsilon

        if not is_training:
            offset = InferValue.expanddims([args[3]], node)
            scale = InferValue.expanddims([AbstractInterpretation(value=args[4].value + epsilon)], node)
            ends_scale_variance = [scale.left / variance.left, scale.right / variance.left,
                                   scale.left / variance.right,
                                   scale.right / variance.right]

            ends = [(x.left - mean.right) * end for end in ends_scale_variance] + [
                (x.right - mean.left) * end for end in ends_scale_variance]

            value = Range(name="fusedbatchnorm", dtype=1)
            return [Range(left=value.left + offset.left, right=value.right + offset.right),
                    Range(name="fusedbatchnorm_mean", dtype=1), Range(name="fusedbatchnorm_variance", dtype=1),
                    Range(name="fusedbatchnorm_rs1", dtype=1), Range(name="fusedbatchnorm_rs2", dtype=1)], z3.And(
                Solver.min(value.left, ends), Solver.max(value.right, ends))
        else:
            ends_scale_variance = [1 / variance.left, 1 / variance.right]

            ends = [(x.left - mean.right) * end for end in ends_scale_variance] + [
                (x.right - mean.left) * end for end in ends_scale_variance]

            value = Range(name="fusedbatchnorm", dtype=1)
            return [value,
                    Range(name="fusedbatchnorm_mean", dtype=1), Range(name="fusedbatchnorm_variance", dtype=1),
                    Range(name="fusedbatchnorm_rs1", dtype=1), Range(name="fusedbatchnorm_rs2", dtype=1)], z3.And(
                Solver.min(value.left, ends), Solver.max(value.right, ends))

    @staticmethod
    def gatherv2(args: list, node):
        assert len(args) == 3
        return InferValue.expanddims(args, node)

    @staticmethod
    def greater(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if not isinstance(args[0].value, Range) and not isinstance(args[1].value, Range):
            return np.greater(args[0].value, args[1].value)
        else:
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            return Range(left=z3.If(x.left > y.right, False, z3.If(x.right <= y.left, True, True)),
                         right=z3.If(x.left > y.right, True, z3.If(x.right <= y.left, False, True))
                         )

    @staticmethod
    def greaterequal(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if not isinstance(args[0].value, Range) and not isinstance(args[1].value, Range):
            return np.greater_equal(args[0].value, args[1].value)
        else:
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            return Range(left=z3.If(x.left >= y.right, False, z3.If(x.right < y.left, True, True)),
                         right=z3.If(x.left >= y.right, True, z3.If(x.right < y.left, False, True))
                         )

    @staticmethod
    def identity(args: list, node):
        assert len(args) == 1
        return args[0].value

    @staticmethod
    def iteratorgetnext(args: list, node):
        assert len(args) == 1
        return args[0].value

    @staticmethod
    def iteratorv2(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, node.op.lower())(node)

    @staticmethod
    def less(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if not isinstance(args[0].value, Range) and not isinstance(args[1].value, Range):
            return np.less(args[0].value, args[1].value)
        else:
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            return Range(left=z3.If(x.left >= y.right, True, z3.If(x.right < y.left, False, True)),
                         right=z3.If(x.left >= y.right, False, z3.If(x.right < y.left, True, True))
                         )

    @staticmethod
    def linspace(args: list, node):
        assert len(args) == 3
        return np.linspace(args[0].value, args[1].value, args[2].value)

    @staticmethod
    def logicaland(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if args[0].value is None or args[1].value is None:
            return
        cond1 = z3.Or(z3.And(args[0].value.left, z3.Not(args[0].value.right)),
                      z3.And(args[1].value.left, z3.Not(args[1].value.right)))
        cond2 = z3.And(z3.Not(args[0].value.left), z3.Not(args[1].value.left), args[0].value.right,
                       args[1].value.right)
        return Range(left=z3.If(cond1, True, z3.If(cond2, False, True)),
                     right=z3.If(cond1, False, z3.If(cond2, True, True)))

    @staticmethod
    def logicalnot(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 1
        return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), False,
                                z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), True, True)),
                     right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), True,
                                 z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), False, True)))

    @staticmethod
    def logicalor(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        assert len(args) == 2
        if args[0].value is None or args[1].value is None:
            return
        cond1 = z3.Or(z3.And(args[0].value.right, z3.Not(args[0].value.left)),
                      z3.And(args[1].value.right, z3.Not(args[1].value.left)))
        cond2 = z3.And(z3.Not(args[0].value.right), z3.Not(args[1].value.right), args[0].value.left,
                       args[1].value.left)
        return Range(left=z3.If(cond1, False, z3.If(cond2, True, True)),
                     right=z3.If(cond1, True, z3.If(cond2, False, True)))
    
    @staticmethod
    def loguniformcandidatesampler(args: list, node):
        assert len(args) == 1
        ind = int(node.attr["range_max"].i)
        num = int(node.attr["num_sampled"].i)
        return [Range(left=0,right=ind - 1), Range(left=UNDERFLOW_LIMIT*10,right=num), Range(left=UNDERFLOW_LIMIT*10,right=num)]

    @staticmethod
    def loopcond(args: list, node):
        return InferValue.identity(args, node)

    @staticmethod
    def matmul(args: list, node):
        assert len(args) == 2 and len(args[0].size) == len(args[1].size)
        for i in range(len(args[0].size) - 2):
            assert str(args[0].size[i]) == "?" or str(args[1].size[i]) == "?" or args[0].size[i] == args[1].size[i]
        ind = real_size(args[0].size[-1], args[1].size[-2])
        if not isinstance(args[0].value, Range) and not isinstance(args[1].value, Range):
            return np.matmul(args[0].value, args[1].value)
        else:
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            value = Range(name="matmul", dtype=args[0].dtype)
            ends = [x.left * y.left * ind, x.left * y.right * ind, x.right * y.left * ind, x.right * y.right * ind]
            return value, z3.And(Solver.min(value.left, ends),
                                 Solver.max(value.right, ends))

    @staticmethod
    def max(args: list, node):
        assert len(args) == 2
        x = args[0].value
        y = args[1].value
        if isinstance(x, Range) and isinstance(y, Range):
            value = Range(name="max", dtype=args[0].dtype)
            return value, z3.And(Solver.max(value.left, [x.left, y.left]),
                                 Solver.max(value.right, [x.right, y.right]))
        elif not isinstance(x, Range) and not isinstance(y, Range):
            return np.maximum(x, y)
        else:
            if isinstance(y, Range):
                x, y = y, x
            y = resolve_type(np.max(y))
            value = Range(name="max", dtype=args[0].dtype)
            return value, z3.And(Solver.max(value.left, [x.left, y]),
                                 Solver.max(value.right, [x.right, y]))

    @staticmethod
    def maxpool(args: list, node):
        assert len(args) == 1
        return args[0].value

    @staticmethod
    def maximum(args: list, node):
        return InferValue.max(args, node)

    @staticmethod
    def mean(args: list, node):
        assert len(args) == 2
        return InferValue.expanddims(args, node)

    @staticmethod
    def merge(args: list, node):
        tmp = InferValue.pack(args, node)
        max_index = int(node.attr["N"].i)
        return_index = Range(left=0, right=max_index - 1)
        if isinstance(tmp, tuple):
            return [tmp[0], return_index], tmp[1]
        else:
            return [tmp, return_index]

    @staticmethod
    def min(args: list, node):
        assert len(args) == 2
        x = args[0].value
        y = args[1].value
        if isinstance(x, Range) and isinstance(y, Range):
            value = Range(name="min", dtype=args[0].dtype)
            return value, z3.And(Solver.min(value.left, [x.left, y.left]),
                                 Solver.min(value.right, [x.right, y.right]))
        elif not isinstance(x, Range) and not isinstance(y, Range):
            return np.minimum(x, y)
        else:
            if isinstance(y, Range):
                x, y = y, x
            y = resolve_type(np.min(y))
            value = Range(name="min", dtype=args[0].dtype)
            return value, z3.And(Solver.min(value.left, [x.left, y]),
                                 Solver.min(value.right, [x.right, y]))

    @staticmethod
    def minimum(args: list, node):
        return InferValue.min(args, node)

    @staticmethod
    def mul(args: list, node):
        assert len(args) == 2
        if args[0].value is None or args[1].value is None:
            return None
        if isinstance(args[1].value, Range) or isinstance(args[0].value, Range):
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            value = Range(name="mul", dtype=args[0].dtype)
            ends = [x.left * y.left, x.left * y.right, x.right * y.left, x.right * y.right]
            return value, z3.And(Solver.min(value.left, ends),
                                 Solver.max(value.right, ends))
        else:
            return args[0].value * args[1].value

    @staticmethod
    def neg(args: list, node):
        assert len(args) == 1
        if isinstance(args[0].value, Range):
            return Range(left=-args[0].value.right, right=-args[0].value.left)
        else:
            return -args[0].value

    @staticmethod
    def nonmaxsuppressionv3(args: list, node):
        assert len(args) == 5
        try:
            ind = int(args[1].size[0])
            return Range(left=0, right=ind - 1)
        except:
            value = Range(left=0, right=Solver.add_variable("nonmaxsuppressionv3_R", 3))
            return value, value.left <= value.right
        
    @staticmethod
    def notequal(args: list, node):
        if not turn_on_bool:
            return Range(left=True, right=True)
        else:
            warnings.warn("floormod not implemented", RuntimeWarning)
            return Range(left=True, right=True)

    @staticmethod
    def onehot(args: list, node):
        assert len(args) == 4
        value = Range(name="onehot", dtype=args[2].dtype)
        constraint = z3.And(Solver.min(value.left, [args[2].value, args[3].value]),
                            Solver.max(value.left, [args[2].value, args[3].value]))
        return value, constraint

    @staticmethod
    def oneshotiterator(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, node.op.lower())(node)

    @staticmethod
    def pack(args: list, node):
        try:
            maxs = [args[i].value.right if isinstance(args[i].value, Range) else resolve_type(np.max(args[i].value)) for
                    i in range(len(args))]
            mins = [args[i].value.left if isinstance(args[i].value, Range) else resolve_type(np.min(args[i].value)) for
                    i in range(len(args))]
            if None in maxs or None in mins:
                return None
            try:
                return Range(left=min(mins), right=max(maxs))
            except:
                value = Range(name="pack", dtype=args[0].dtype)
                return value, z3.And(Solver.min(value.left, mins), Solver.max(value.right, maxs))
        except:
            # boolean
            has_zero = []
            has_one = []
            for i in range(len(args)):
                if isinstance(args[i].value, Range):
                    has_zero.append(args[i].value.left)
                    has_one.append(args[i].value.right)
                else:
                    has_zero.append(not bool(np.all(args[i].value)))
                    has_one.append(bool(np.any(args[i].value)))
            return Range(left=z3.Or(has_zero), right=z3.Or(has_one))

    @staticmethod
    def pad(args: list, node):
        return InferValue.expanddims(args, node)

    @staticmethod
    def placeholder(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, node.op.lower())(node)

    @staticmethod
    def prod(args: list, node):
        assert len(args) == 2
        return InferValue.mul(args, node)

    @staticmethod
    def randomshuffle(args: list, node):
        assert len(args) == 1
        return InferValue.expanddims(args, node)

    @staticmethod
    def randomuniform(args: list, node):
        assert len(args) == 1
        value = Range(name="randomuniform", dtype=1)
        return Range(left=UNDERFLOW_LIMIT * 10, right=1)

    @staticmethod
    def range(args: list, node):
        assert len(args) == 3
        left = args[0].value.left if isinstance(args[0].value, Range) else int(args[0].value)
        right = args[1].value.right if isinstance(args[1].value, Range) else int(args[1].value)
        return Range(left=left, right=right)
    
    @staticmethod
    def rank(args: list, node):
        assert len(args) == 1
        try:
            return int(args[0].size)
        except:
            value = Range(left=1, right=Solver.add_variable("rank3_R", 3))
            return value, value.left <= value.right

    @staticmethod
    def readvariableop(args: list, node):
        assert len(args) == 1
        return args[0].value

    @staticmethod
    def realdiv(args: list, node):
        assert len(args) == 2
        try:
            x = float(args[0].value)
        except:
            x = InferValue.expanddims([args[0]], node)
        try:
            y = float(args[1].value)
        except:
            y = InferValue.expanddims([args[1]], node)

        if isinstance(x, Range) and isinstance(y, Range):
            ends = [x.left / y.left, x.left / y.right, x.right / y.left, x.right / y.right]
            value = Range(name="realdiv", dtype=args[0].dtype)
            return value, z3.And(Solver.min(value.left, ends),
                                 Solver.max(value.right, ends))
        elif not isinstance(y, Range):
            return x * (1 / y)
        else:
            ends = [x / y.left, x / y.right]
            value = Range(name="realdiv", dtype=args[0].dtype)
            return value, z3.And(Solver.min(value.left, ends),
                                 Solver.max(value.right, ends))

    @staticmethod
    def relu(args: list, node):
        assert len(args) == 1
        value = Range(name="relu", dtype=args[0].dtype)
        return value, z3.And(Solver.max(value.left, [args[0].value.left, 0]),
                             Solver.max(value.right, [args[0].value.right, 0]))

    @staticmethod
    def relu6(args: list, node):
        assert len(args) == 1
        return Range(left=z3.If(args[0].value.left < 0, 0, z3.If(args[0].value.left > 6, 6, args[0].value.left)),
                     right=z3.If(args[0].value.right < 0, 0, z3.If(args[0].value.right > 6, 6, args[0].value.right)))

    @staticmethod
    def reshape(args: list, node):
        assert len(args) == 2
        return InferValue.expanddims(args, node)

    @staticmethod
    def reversev2(args: list, node):
        assert len(args) == 2
        return InferValue.expanddims(args, node)

    @staticmethod
    def rsqrt(args: list, node):
        assert len(args) == 1
        if isinstance(args[0].value, Range):
            cons = []
            try:
                left = math.sqrt(args[0].value.left)
            except:
                left = Solver.add_variable("rsqrtL", 1)
                cons.append(left >= 0)
                cons.append(left * left == args[0].value.left)

            try:
                right = math.sqrt(args[0].value.right)
            except:
                right = Solver.add_variable("rsqrtR", 1)
                cons.append(right >= 0)
                cons.append(right * right == args[0].value.right)

            return Range(left=1 / right, right=1 / left), z3.And(cons)
        else:
            return 1 / math.sqrt(args[0].value)

    @staticmethod
    def select(args: list, node):
        assert len(args) == 3
        if not isinstance(args[0].value, Range):
            # print(args[0].value)
            raise NotImplementedError("not implemented when the condition is known")
        x = InferValue.expanddims([args[1]], node)
        y = InferValue.expanddims([args[2]], node)
        if not turn_on_bool:
            return Range(left=z3.If(x.left < y.left, x.left, y.left), right=z3.If(x.right > y.right, x.right, y.right))
        return Range(left=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), x.left,
                                z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), y.left,
                                      z3.If(x.left < y.left, x.left, y.left))),
                     right=z3.If(z3.And(args[0].value.left, z3.Not(args[0].value.right)), x.right,
                                 z3.If(z3.And(args[0].value.right, z3.Not(args[0].value.left)), y.right,
                                       z3.If(x.right > y.right, x.right, y.right))))

    @staticmethod
    def shape(args: list, node):
        assert len(args) == 1
        try:
            return [int(x) for x in args[0].size]
        except:
            value = Range(left=0, right=Solver.add_variable("shape_R", 3))
            return value, value.left < value.right

    @staticmethod
    def size(args: list, node):
        assert len(args) == 1
        try:
            ele = 1
            for x in args[0].size:
                ele *= int(x)
            if ele < 0:
                value = Range(left=0, right=Solver.add_variable("size_R", 3))
                return value, value.left < value.right
            else:
                return ele
        except:
            value = Range(left=0, right=Solver.add_variable("size_R", 3))
            return value, value.left < value.right

    @staticmethod
    def slice(args: list, node):
        return InferValue.expanddims(args, node)

    @staticmethod
    def split(args: list, node):
        assert len(args) == 2
        nums = int(node.attr["num_split"].i)
        if nums == 1:
            return InferValue.expanddims(args[1:], node)
        else:
            return [InferValue.expanddims(args[1:], node) for _ in range(nums)]

    @staticmethod
    def sqrt(args: list, node):
        assert len(args) == 1
        if isinstance(args[0].value, Range):
            cons = []
            try:
                left = math.sqrt(args[0].value.left)
            except:
                left = Solver.add_variable("sqrtL", 1)
                cons.append(left >= 0)
                cons.append(left * left == args[0].value.left)

            try:
                right = math.sqrt(args[0].value.right)
            except:
                right = Solver.add_variable("sqrtR", 1)
                cons.append(right >= 0)
                cons.append(right * right == args[0].value.right)

            return Range(left=left, right=right), z3.And(cons)
        else:
            return np.sqrt(args[0].value)

    @staticmethod
    def squareddifference(args: list, node):
        assert len(args) == 2
        value1 = (args[0].value.left - args[1].value.right) * (args[0].value.left - args[1].value.right)
        value2 = (args[0].value.right - args[1].value.left) * (args[0].value.right - args[1].value.left)
        return Range(left=z3.If(
            z3.Or(z3.And(args[0].value.left >= args[1].value.left, args[0].value.left <= args[1].value.right),
                  z3.And(args[0].value.right >= args[1].value.left, args[0].value.right <= args[1].value.right)), 0,
            z3.If(value1 < value2, value1, value2)), right=z3.If(value1 > value2, value1, value2))

    @staticmethod
    def squeeze(args: list, node):
        assert len(args) == 1
        return InferValue.expanddims(args, node)

    @staticmethod
    def stopgradient(args: list, node):
        return InferValue.identity(args, node)

    @staticmethod
    def stridedslice(args: list, node):
        return InferValue.expanddims(args, node)

    @staticmethod
    def sub(args: list, node):
        assert len(args) == 2
        if isinstance(args[0].value, Range) or isinstance(args[1].value, Range):
            x = InferValue.expanddims([args[0]], node)
            y = InferValue.expanddims([args[1]], node)
            return Range(left=x.left - y.right, right=x.right - y.left)
        else:
            return args[0].value - args[1].value

    @staticmethod
    def sum(args: list, node):
        assert len(args) == 2
        if args[0].value is None:
            return None
        if isinstance(args[0].value, Range):
            try:
                ind = int(args[0].size[int(args[1].value)])
                return Range(left=args[0].value.left * ind, right=args[0].value.right * ind)
            except:
                ind = Range(name="sum_ind", dtype=3)
                ind.left = 0
                t = InferValue.mul([args[0], AbstractInterpretation(value=ind, dtype=3, size=[])], node)
                if isinstance(t, tuple):
                    return t[0], z3.And(t[1], ind.right >= 0)
                else:
                    return t, ind.right >= ind.left
        else:
            return np.sum(args[0].value, axis=args[1].value)

    @staticmethod
    def switch(args: list, node):
        assert len(args) == 2
        return [args[0].value, args[0].value]

    @staticmethod
    def tensorarraygatherv3(args: list, node):
        assert len(args) == 3
        return args[0].value

    @staticmethod
    def tensorarrayv3(args: list, node):
        assert len(args) == 1
        return [Range(name="tensorarrayv3", dtype=node.attr["dtype"].type),
                Range(name="tensorarrayv3_dumy", dtype=node.attr["dtype"].type)]

    @staticmethod
    def tensorarrayreadv3(args: list, node):
        assert len(args) == 3
        return args[0].value

    @staticmethod
    def tensorarrayscatterv3(args: list, node):
        assert len(args) == 4
        if isinstance(args[2].value, Range):
            return args[0].value, z3.And(args[0].value.left <= args[2].value.left,
                                         args[0].value.right >= args[2].value.right)
        else:
            return args[0].value, z3.And(args[0].value.left <= args[2].value,
                                         args[0].value.right >= args[2].value)

    @staticmethod
    def tensorarraysizev3(args: list, node):
        assert len(args) == 2
        return int(args[0].size[0])

    @staticmethod
    def tensorarraywritev3(args: list, node):
        assert len(args) == 4
        return InferValue.tensorarrayscatterv3(args, node)

    @staticmethod
    def tile(args: list, node):
        assert len(args) == 2
        return InferValue.expanddims(args, node)

    @staticmethod
    def topkv2(args: list, node):
        assert len(args) == 2
        try:
            ind = int(args[0].size[-1])
            value = Range(left=0, right=ind - 1)
        except:
            value = Range(left=0, right=Solver.add_variable(name="topkv2_R", dtype=3))
        return [InferValue.expanddims(args, node), value]

    @staticmethod
    def transpose(args: list, node):
        assert len(args) == 2
        return InferValue.expanddims(args, node)

    @staticmethod
    def unpack(args: list, node):
        assert len(args) == 1
        nums = int(node.attr["num"].i)
        if nums == 1:
            return InferValue.expanddims(args, node)
        else:
            return [InferValue.expanddims(args, node) for _ in range(nums)]

    @staticmethod
    def varhandleop(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, "variablev2")(node)

    @staticmethod
    def variable(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, "variablev2")(node)

    @staticmethod
    def variablev2(args: list, node):
        assert len(args) == 0
        return getattr(parse_format_text, node.op.lower())(node)

    @staticmethod
    def where(args: list, node):
        assert len(args) == 1
        try:
            x = np.max(args[0].size)
            return Range(left=0, right=x - 1)
        except:
            x = Solver.add_variable("where", 3)
            return Range(left=0, right=x - 1), x > 1

    @staticmethod
    def zeroslike(args: list, node):
        assert len(args) == 1
        return Range(left=0, right=0)

    @staticmethod
    def floormod(args: list, node):
        warnings.warn("floormod not implemented", RuntimeWarning)

    @staticmethod
    def iteratortostringhandle(args: list, node):
        warnings.warn("iteratortostringhandle not implemented", RuntimeWarning)

    @staticmethod
    def noop(args: list, node):
        warnings.warn("noop not implemented", RuntimeWarning)

    @staticmethod
    def restorev2(args: list, node):
        warnings.warn("restorev2 not implemented", RuntimeWarning)

    @staticmethod
    def savev2(args: list, node):
        warnings.warn("savev2 not implemented", RuntimeWarning)

    # non linear operations:
    @staticmethod
    def log(args: list, node):
        assert len(args) == 1
        stride = 15
        intervals = [(0, math.pow(10, UNDERFLOW_D))] + \
                    [(math.pow(10, i), math.pow(10, i + stride)) for i in range(UNDERFLOW_D, OVERFLOW_D, stride)] + \
                    [(math.pow(10, OVERFLOW_D), math.inf)]
        if isinstance(args[0].value, Range):
            value = Range(name="log", dtype=1)
            constraints = []
            for (left, right) in combinations_with_replacement(intervals, 2):
                temp_constraint = [Solver.in_interval(args[0].value.left, left),
                                   Solver.in_interval(args[0].value.right, right)]
                if left[0] != 0:
                    temp_constraint += [value.left == math.log(left[0])]
                if not math.isinf(right[1]):
                    temp_constraint += [value.right == math.log(right[1])]
                constraints.append(z3.And(temp_constraint))

            return value, z3.And(z3.Or(constraints), value.left <= value.right)
        else:
            return math.log(args[0].value)

    @staticmethod
    def exp(args: list, node):
        assert len(args) == 1
        intervals = [(-math.inf, -90), (-90, -5), (-5, 5), (5, 90), (90, math.inf)]
        if isinstance(args[0].value, Range):
            value = Range(name="exp", dtype=1)
            constraints = []
            for (left, right) in combinations_with_replacement(intervals, 2):
                temp_constraint = [Solver.in_interval(args[0].value.left, left),
                                   Solver.in_interval(args[0].value.right, right)]
                if not math.isinf(np.min(left)):
                    temp_constraint += [value.left == math.exp(np.min(left))]
                else:
                    temp_constraint += [value.left == 0]
                if not math.isinf(np.max(right)):
                    temp_constraint += [value.right == math.exp(np.max(right))]
                constraints.append(z3.And(temp_constraint))

            return value, z3.And(z3.Or(constraints), value.left <= value.right)
        else:
            return math.exp(args[0].value)

    @staticmethod
    def softmax(args: list, node):
        assert len(args) == 1
        ind = int(args[0].size[-1])
        assert ind > 1
        intervals = [(-math.inf, -90), (-90, -1), (-1, 1), (1, 90), (90, math.inf)]
        if isinstance(args[0].value, Range):
            value = Range(name="softmax", dtype=1)
            constraints = []
            for (left, right) in combinations_with_replacement(intervals, 2):
                temp_constraint = [Solver.in_interval(args[0].value.left, left),
                                   Solver.in_interval(args[0].value.right, right)]
                min_ele = math.exp(np.min(left)) if not math.isinf(np.min(left)) else 0
                max_ele = math.exp(np.max(right)) if not math.isinf(np.max(right)) else math.inf
                if isinstance(left, tuple) or isinstance(right, tuple):
                    if math.isinf(max_ele) or min_ele == 0:
                        temp_constraint += [value.left == 0]
                    else:
                        temp_constraint += [value.left == min_ele / ((ind - 1) * max_ele + min_ele)]
                    if math.isinf(max_ele) or min_ele == 0:
                        temp_constraint += [value.right == 1]
                    else:
                        temp_constraint += [value.right == max_ele / ((ind - 1) * min_ele + max_ele)]
                else:
                    temp_constraint += [value.left == 1.0 / ind, value.right == 1.0 / ind]

                constraints.append(z3.And(temp_constraint))

            return value, z3.Or(constraints)
        else:
            tmp_exp = np.exp(args[0].value)
            return tmp_exp / np.sum(tmp_exp)

    @staticmethod
    def sigmoid(args: list, node):
        assert len(args) == 1
        intervals = [(-math.inf, -40), (-40, -2), (-2, 2), (2, 40), (40, math.inf)]
        if isinstance(args[0].value, Range):
            value = Range(name="sigmoid", dtype=1)
            pre_left = None
            pre_right = None
            for interval in intervals:
                if not math.isinf(np.min(interval)):
                    left = 1 / (1 + math.exp(-np.min(interval)))
                else:
                    left = 0
                if not math.isinf(np.max(interval)):
                    right = 1 / (1 + math.exp(-np.max(interval)))
                else:
                    right = 1

                if pre_left is None:
                    pre_left = left
                else:
                    pre_left = z3.If(Solver.in_interval(args[0].value.left, interval), left, pre_left)
                if pre_right is None:
                    pre_right = right
                else:
                    pre_right = z3.If(Solver.in_interval(args[0].value.right, interval), right, pre_right)

            return value, z3.And(value.left == pre_left, value.right == pre_right, value.left <= value.right)
        else:
            return 1 / (1 + np.exp(-args[0].value))

    @staticmethod
    def tanh(args: list, node):
        assert len(args) == 1
        intervals = [(-math.inf, -20), (-20, -1), (-1, 1), (1, 20), (20, math.inf)]
        if isinstance(args[0].value, Range):
            value = Range(name="tanh", dtype=1)
            pre_left = None
            pre_right = None
            for interval in intervals:
                if not math.isinf(np.min(interval)):
                    left = math.tanh(np.min(interval))
                else:
                    left = -1
                if not math.isinf(np.max(interval)):
                    right = math.tanh(np.max(interval))
                else:
                    right = 1

                if pre_left is None:
                    pre_left = left
                else:
                    pre_left = z3.If(Solver.in_interval(args[0].value.left, interval), left, pre_left)
                if pre_right is None:
                    pre_right = right
                else:
                    pre_right = z3.If(Solver.in_interval(args[0].value.right, interval), right, pre_right)

            return value, z3.And(value.left == pre_left, value.right == pre_right, value.left <= value.right)
        else:
            return np.tanh(args[0].value)


class InferArray:
    @staticmethod
    def add(args: list, node):
        try:
            len(args[0].size) == len(args[1].size)
        except:
            return None
        assert len(args) == 2 and len(args[0].size) == len(args[1].size)
        ind = len(args[0].size)
        for i in range(ind):
            assert args[0].size[i] == args[1].size[i]
        ret = Array("tmp", args[0].size)
        ret.block_to_symbol = dict()
        ret.index_slices = Array.join_index_slices(args[0].array.index_slices, args[1].array.index_slices)
        keys0 = args[0].array.get_corresponding_keys(ret.index_slices)
        keys1 = args[1].array.get_corresponding_keys(ret.index_slices)
        i = 0
        for indexes in product(*ret.index_slices):
            ret.block_to_symbol[tuple(indexes)] = keys0[i] + keys1[i]
            i += 1

        return ret

    @staticmethod
    def concatv2(args: list, node):
        assert len(args) > 1
        if len(args) - 1 > 10:
            return None
        concat_ind = int(args[-1].value)
        for i in range(1, len(args) - 1):
            assert len(args[0].size) == len(args[i].size)
            for j in range(len(args[i].size)):
                try:
                    int(args[0].size[j])
                    int(args[i].size[j])
                except:
                    return None
                if j != concat_ind:
                    assert int(args[0].size[j]) == int(args[i].size[j])

        ret = Array("tmp", args[0].size)
        ret.block_to_symbol = dict()
        index_slices = []
        for arg in args[:-1]:
            index_slices.append(copy.deepcopy(arg.array.index_slices))
            index_slices[-1][concat_ind] = [None]

        ret.index_slices = index_slices[0]
        for i in range(1, len(args) - 1):
            ret.index_slices = Array.join_index_slices(ret.index_slices, index_slices[i])
        tmp_ret_index_slices = copy.deepcopy(ret.index_slices)
        ret.index_slices[concat_ind] = []
        split_point = 0
        for i in range(len(args) - 1):
            tmp_ret_index_slices[concat_ind] = args[i].array.index_slices[concat_ind]
            ret.index_slices[concat_ind] += list(np.array(args[i].array.index_slices[concat_ind]) + split_point)
            tmp_keys = args[i].array.get_corresponding_keys(tmp_ret_index_slices)
            tmp_ret_index_slices[concat_ind] = list(np.array(args[i].array.index_slices[concat_ind]) + split_point)
            split_point += int(args[i].array.index_slices[concat_ind][-1])
            ii = 0
            for indexes in product(*tmp_ret_index_slices):
                ret.block_to_symbol[tuple(indexes)] = tmp_keys[ii]
                ii += 1

        return ret

    @staticmethod
    def identity(args: list, node):
        assert len(args) == 1
        return args[0].array

    @staticmethod
    def pack(args: list, node):
        # return InferArray.concatv2(args + [AbstractInterpretation(value=len(args[0].size) - 1)], node)
        assert len(args) >= 1
        if len(args) > 10:
            return None
        pack_ind = int(node.attr["axis"].i)
        for i in range(1, len(args)):
            try:
                len(args[0].size) == len(args[i].size)
            except:
                return None
            assert len(args[0].size) == len(args[i].size)
            for j in range(len(args[i].size)):
                try:
                    int(args[0].size[j])
                    int(args[i].size[j])
                except:
                    return None
                assert int(args[0].size[j]) == int(args[i].size[j])

        ret = Array("tmp", args[0].size)
        ret.block_to_symbol = dict()
        index_slices = []
        for arg in args:
            index_slices.append(copy.deepcopy(arg.array.index_slices))
        ret.index_slices = index_slices[0]
        for i in range(1, len(args)):
            ret.index_slices = Array.join_index_slices(ret.index_slices, index_slices[i])
        tmp_ret_index_slices = copy.deepcopy(ret.index_slices)
        ret.index_slices = ret.index_slices[:pack_ind] + [[]] + ret.index_slices[pack_ind:]

        for i in range(len(args)):
            ret.index_slices[pack_ind] += [i + 1]
            tmp_keys = args[i].array.get_corresponding_keys(tmp_ret_index_slices)
            ii = 0
            for indexes in product(*tmp_ret_index_slices):
                tmp_key = list(indexes)
                tmp_key = tmp_key[:pack_ind] + [i + 1] + tmp_key[pack_ind:]
                ret.block_to_symbol[tuple(tmp_key)] = tmp_keys[ii]
                ii += 1

        return ret

    @staticmethod
    def sub(args: list, node):
        try:
            len(args[0].size) == len(args[1].size)
        except:
            return None
        assert len(args) == 2 and len(args[0].size) == len(args[1].size)
        ind = len(args[0].size)
        for i in range(ind):
            assert args[0].size[i] == args[1].size[i]

        ret = Array("tmp", args[0].size)
        ret.block_to_symbol = dict()
        ret.index_slices = Array.join_index_slices(args[0].array.index_slices, args[1].array.index_slices)
        keys0 = args[0].array.get_corresponding_keys(ret.index_slices)
        keys1 = args[1].array.get_corresponding_keys(ret.index_slices)
        i = 0
        for indexes in product(*ret.index_slices):
            ret.block_to_symbol[tuple(indexes)] = keys0[i] - keys1[i]
            i += 1

        return ret

    @staticmethod
    def transpose(args: list, node):
        assert len(args) == 2
        assert not isinstance(args[1].value, Range)
        ret = Array("tmp", args[0].size)
        ret.index_slices = []
        ret.block_to_symbol = {}
        for x in np.array(args[1].value):
            ret.index_slices.append(args[0].array.index_slices[x])
        for indexes in product(*args[0].array.index_slices):
            new_indexes = ()
            for x in np.array(args[1].value):
                new_indexes += (indexes[x],)

            ret.block_to_symbol[new_indexes] = args[0].array.block_to_symbol[tuple(indexes)]

        return ret

    @staticmethod
    def unpack(args: list, node):
        assert len(args) == 1
        axis = int(node.attr["axis"].i)
        rets = []
        index_slices = copy.deepcopy(args[0].array.index_slices)
        try:
            if int(args[0].size[axis]) > 10:
                return None
        except:
            return None
        
        for i in range(int(args[0].size[axis])):
            rets.append(Array("tmp", args[0].size))
            rets[-1].index_slices = copy.deepcopy(args[0].array.index_slices)
            rets[-1].index_slices = rets[-1].index_slices[:axis] + rets[-1].index_slices[axis + 1:]
            rets[-1].block_to_symbol = {}

            index_slices[axis] = [i]
            tmp_keys = args[0].array.get_corresponding_keys(index_slices)
            ii = 0
            for indexes in product(*index_slices):
                tmp_key = list(indexes)
                tmp_key = tmp_key[:axis] + tmp_key[axis + 1:]
                rets[-1].block_to_symbol[tuple(tmp_key)] = tmp_keys[ii]
                ii += 1

        return rets if len(rets) > 1 else rets[0]

    @staticmethod
    def split(args: list, node):
        assert len(args) == 2
        axis = int(args[0].value)
        rets = []
        index_slices = copy.deepcopy(args[1].array.index_slices)
        try:
            if int(args[1].size[axis]) > 10:
                return None
        except:
            return None
        
        for i in range(int(args[1].size[axis])):
            rets.append(Array("tmp", args[1].size))
            rets[-1].index_slices = copy.deepcopy(args[1].array.index_slices)
            rets[-1].index_slices[axis] = [1]
            rets[-1].block_to_symbol = {}

            index_slices[axis] = [i]
            tmp_keys = args[1].array.get_corresponding_keys(index_slices)
            ii = 0
            for indexes in product(*index_slices):
                tmp_key = list(indexes)
                tmp_key[axis] = 1
                rets[-1].block_to_symbol[tuple(tmp_key)] = tmp_keys[ii]
                ii += 1

        return rets if len(rets) > 1 else rets[0]
